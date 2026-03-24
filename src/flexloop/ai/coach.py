import json
import logging

from flexloop.ai.base import LLMAdapter, LLMResponse
from flexloop.ai.prompts import PromptManager
from flexloop.ai.validators import validate_plan_output, validate_review_output
from flexloop.config import settings

logger = logging.getLogger(__name__)


class AICoach:
    def __init__(self, adapter: LLMAdapter, prompt_manager: PromptManager):
        self.adapter = adapter
        self.prompts = prompt_manager

    async def generate_plan(self, user_profile: str) -> tuple[dict | None, LLMResponse]:
        prompt = self.prompts.render(
            "plan_generation",
            provider=settings.ai_provider,
            user_profile=user_profile,
        )

        response = await self.adapter.generate(
            system_prompt="You are a fitness plan generator. Respond only with valid JSON.",
            user_prompt=prompt,
            temperature=settings.ai_temperature,
            max_tokens=settings.ai_max_tokens,
        )

        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            logger.warning("AI returned non-JSON response for plan generation")
            return None, response

        validation = validate_plan_output(data)
        if not validation.is_valid:
            logger.warning(f"AI plan output validation failed: {validation.errors}")
            return None, response

        return data, response

    async def review_block(
        self, user_profile: str, training_data: str, volume_landmarks: str,
    ) -> tuple[dict | None, LLMResponse]:
        prompt = self.prompts.render(
            "block_review",
            provider=settings.ai_provider,
            user_profile=user_profile,
            training_data=training_data,
            volume_landmarks=volume_landmarks,
        )

        response = await self.adapter.generate(
            system_prompt=(
                "You are a fitness coach reviewing training data. "
                "Respond only with valid JSON."
            ),
            user_prompt=prompt,
            temperature=settings.ai_temperature,
            max_tokens=settings.ai_max_tokens,
        )

        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            logger.warning("AI returned non-JSON response for block review")
            return None, response

        validation = validate_review_output(data)
        if not validation.is_valid:
            logger.warning(f"AI review output validation failed: {validation.errors}")
            return None, response

        return data, response

    async def chat(
        self, messages: list[dict], user_profile: str,
        current_plan: str, training_history: str,
    ) -> LLMResponse:
        system_prompt = self.prompts.render(
            "chat",
            provider=settings.ai_provider,
            user_profile=user_profile,
            current_plan=current_plan,
            training_history=training_history,
        )

        full_messages = [{"role": "system", "content": system_prompt}] + messages

        return await self.adapter.chat(
            messages=full_messages,
            temperature=settings.ai_temperature,
            max_tokens=settings.ai_max_tokens,
        )
