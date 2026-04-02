import asyncio
import logging
import os
import random
from contextlib import asynccontextmanager
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from ai_engine import AIEngine
from database import ProcessedComment, engine, init_db, is_processed, mark_processed
from facebook_client import FacebookClient
from sqlalchemy.orm import Session

load_dotenv()

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_DIR = os.getenv("LOG_DIR", "./logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "errors.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
# Only WARNING+ goes to the error log file
file_handler = logging.root.handlers[-1]
file_handler.setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FB_PAGE_ACCESS_TOKEN = os.environ["FB_PAGE_ACCESS_TOKEN"]
FB_VERIFY_TOKEN = os.environ["FB_VERIFY_TOKEN"]
PAGE_ID = os.environ["PAGE_ID"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------

fb_client: FacebookClient
ai_engine: AIEngine


@asynccontextmanager
async def lifespan(app: FastAPI):
    global fb_client, ai_engine
    init_db()
    fb_client = FacebookClient(page_access_token=FB_PAGE_ACCESS_TOKEN, page_id=PAGE_ID)
    ai_engine = AIEngine(openai_api_key=OPENAI_API_KEY)
    logger.info("Facebook Auto-Responder started.")
    yield
    logger.info("Facebook Auto-Responder stopped.")


app = FastAPI(title="Facebook Auto-Responder", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/stats")
async def get_stats():
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(engine) as session:
        total_replied = session.query(ProcessedComment).filter(
            ProcessedComment.action == "replied"
        ).count()
        total_skipped = session.query(ProcessedComment).filter(
            ProcessedComment.action == "skipped"
        ).count()
        total_random_skip = session.query(ProcessedComment).filter(
            ProcessedComment.action == "random_skip"
        ).count()
        today_replied = session.query(ProcessedComment).filter(
            ProcessedComment.action == "replied",
            ProcessedComment.processed_at >= today_start,
        ).count()
    return {
        "total_replied": total_replied,
        "total_skipped": total_skipped,
        "total_random_skip": total_random_skip,
        "today_replied": today_replied,
    }


@app.get("/webhook")
async def webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == FB_VERIFY_TOKEN:
        logger.info("Webhook verified by Meta.")
        return PlainTextResponse(content=hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def webhook_receive(request: Request):
    body = await request.json()

    if body.get("object") != "page":
        return JSONResponse({"status": "ignored"})

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            # Only process new comments (not edits, likes, etc.)
            if value.get("item") != "comment" or value.get("verb") != "add":
                continue

            from_id = value.get("from", {}).get("id", "")
            # Ignore comments from the Page itself (anti-loop)
            if from_id == PAGE_ID:
                continue

            comment_id = value.get("comment_id", "")
            post_id = value.get("post_id", "")
            message = value.get("message", "")

            if comment_id and message:
                asyncio.create_task(
                    process_comment(comment_id, post_id, message, from_id)
                )

    return JSONResponse({"status": "ok"})


@app.post("/sync-recent")
async def sync_recent():
    posts = fb_client.get_recent_posts_with_comments()
    scheduled = 0

    for post in posts:
        for comment in post["comments"]:
            from_id = comment["from_id"]
            if from_id == PAGE_ID:
                continue
            comment_id = comment["id"]
            message = comment["message"]
            if comment_id and message:
                asyncio.create_task(
                    process_comment(comment_id, post["post_id"], message, from_id)
                )
                scheduled += 1

    return {"status": "ok", "scheduled": scheduled}


@app.get("/logs")
async def get_logs(lines: int = Query(100, ge=1, le=5000)):
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            all_lines = f.readlines()
        tail = "".join(all_lines[-lines:])
        return PlainTextResponse(content=tail or "(log vide)")
    except FileNotFoundError:
        return PlainTextResponse(content="(log vide)")


# ---------------------------------------------------------------------------
# Core processing logic
# ---------------------------------------------------------------------------


async def process_comment(
    comment_id: str,
    post_id: str,
    message: str,
    from_id: str,
) -> None:
    # 1. Anti-doublon
    if is_processed(comment_id):
        return

    # 2. Analyse IA
    response_text = await asyncio.to_thread(ai_engine.analyze_comment, message)

    # 3. Filtrage SKIP
    if response_text.upper() == "SKIP":
        mark_processed(comment_id, post_id, "skipped")
        logger.info("Comment %s skipped by AI.", comment_id)
        return

    # 4. Taux de réponse 80%
    if random.random() >= 0.8:
        mark_processed(comment_id, post_id, "random_skip")
        logger.info("Comment %s randomly skipped (20%% gate).", comment_id)
        return

    # 5. Délai humain (30s–5min)
    delay = random.randint(30, 300)
    logger.info("Comment %s: waiting %ds before reply.", comment_id, delay)
    await asyncio.sleep(delay)

    # 6. Envoi de la réponse
    success = await asyncio.to_thread(
        fb_client.reply_to_comment, comment_id, response_text
    )

    # 7. Enregistrement en base
    if success:
        mark_processed(comment_id, post_id, "replied")
        logger.info("Comment %s replied successfully.", comment_id)
    else:
        logger.warning("Comment %s reply failed after retries.", comment_id)
        # Ne pas marquer comme traité pour permettre une future tentative via /sync-recent
