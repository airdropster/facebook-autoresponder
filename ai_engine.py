import logging
from openai import OpenAI, APIError

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Tu es un assistant bienveillant qui gère les commentaires Facebook d'une page. "
    "Réponds uniquement en français, de façon courte et décontractée (1-2 phrases max). "
    "Si le commentaire est agressif, négatif ou du spam, réponds UNIQUEMENT avec le mot SKIP."
)


class AIEngine:
    def __init__(self, openai_api_key: str) -> None:
        self.client = OpenAI(api_key=openai_api_key)

    def analyze_comment(self, comment_text: str) -> str:
        """
        Analyse un commentaire et retourne soit "SKIP" soit une réponse courte en français.
        En cas d'erreur API, retourne "SKIP" par sécurité.
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": comment_text},
                ],
                max_tokens=100,
                temperature=0.7,
            )
            result = response.choices[0].message.content or ""
            return result.strip()
        except APIError as exc:
            logger.error("OpenAI APIError analyzing comment: %s", exc)
            return "SKIP"
        except Exception as exc:
            logger.error("Unexpected error in analyze_comment: %s", exc)
            return "SKIP"
