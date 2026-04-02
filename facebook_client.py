import logging
import time
import requests

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com/v19.0"


class FacebookClient:
    def __init__(self, page_access_token: str, page_id: str) -> None:
        self.token = page_access_token
        self.page_id = page_id

    def reply_to_comment(self, comment_id: str, message: str) -> bool:
        """Post a reply to a comment. Returns True on success."""
        url = f"{GRAPH_BASE}/{comment_id}/comments"
        payload = {"message": message, "access_token": self.token}

        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, timeout=10)
                resp.raise_for_status()
                return True
            except requests.RequestException as exc:
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                logger.warning(
                    "reply_to_comment attempt %d/3 failed for %s: %s. Retrying in %ds.",
                    attempt + 1,
                    comment_id,
                    exc,
                    wait,
                )
                if attempt < 2:
                    time.sleep(wait)

        logger.error("reply_to_comment failed after 3 attempts for comment %s", comment_id)
        return False

    def get_recent_posts_with_comments(self) -> list[dict]:
        """
        Fetch the 3 most recent posts with their comments.
        Returns a list of:
          {"post_id": str, "comments": [{"id": str, "message": str, "from_id": str}]}
        """
        url = f"{GRAPH_BASE}/{self.page_id}/feed"
        params = {
            "fields": "id,message,comments{id,message,from}",
            "limit": 3,
            "access_token": self.token,
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("get_recent_posts_with_comments failed: %s", exc)
            return []

        data = resp.json()
        result = []

        for post in data.get("data", []):
            post_id = post.get("id", "")
            comments_raw = post.get("comments", {}).get("data", [])
            comments = [
                {
                    "id": c["id"],
                    "message": c.get("message", ""),
                    "from_id": c.get("from", {}).get("id", ""),
                }
                for c in comments_raw
                if c.get("from", {}).get("id")
            ]
            if comments:
                result.append({"post_id": post_id, "comments": comments})

        return result
