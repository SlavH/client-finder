"""LLM integration via litellm with humanization support."""

from __future__ import annotations

from typing import Any

import litellm

from client_finder.config import get_api_key


class LLMClient:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        llm_cfg = config.get("llm", {})
        self.provider = llm_cfg.get("provider", "openai")
        self.model = llm_cfg.get("model", "gpt-4o-mini")
        self.temperature = llm_cfg.get("temperature", 0.7)
        self.max_tokens = llm_cfg.get("max_tokens", 1500)
        self.base_url = llm_cfg.get("base_url")
        self.api_key = get_api_key(config)

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Call the LLM and return the text response."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url

        response = litellm.completion(**kwargs)
        return response.choices[0].message.content or ""

    def score_lead(
        self,
        lead_summary: str,
        profile_summary: str,
        avoid_patterns: list[str],
    ) -> dict[str, Any]:
        """Score a lead and return fit_score, reason, hook, pain_point, suggested_role."""
        system = (
            "You are a lead-scoring assistant for a freelancer/agency. "
            "Given a lead summary and a seller profile, output a JSON object with:\n"
            "- fit_score: integer 0-100\n"
            "- fit_reason: short string\n"
            "- hook: one-sentence personalized opening based on a real detail from the lead\n"
            "- pain_point: the lead's likely problem (one sentence)\n"
            "- suggested_role: who to contact (job title)\n"
            "Be specific. Cite actual details from the lead. Do not hallucinate."
        )
        user = (
            f"LEAD:\n{lead_summary}\n\n"
            f"SELLER PROFILE:\n{profile_summary}\n\n"
            "Return ONLY valid JSON."
        )
        text = self.complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
        )
        return self._parse_json(text)

    def draft_message(
        self,
        lead: dict[str, Any],
        profile_summary: str,
        tone: dict[str, Any],
        channel: str,
        mode: str,
        deliverable_description: str | None = None,
        contact_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Draft a humanized outreach message. Returns {subject, body}."""
        avoid = tone.get("avoid_patterns", [])
        system = (
            "You write cold outreach messages that sound like a real human wrote them. "
            "Rules:\n"
            "- No AI clichés: never use " + ", ".join(f'"{p}"' for p in avoid) + "\n"
            "- Short paragraphs (max 3 sentences)\n"
            "- Use contractions naturally\n"
            "- Reference a REAL detail from the lead (the hook)\n"
            "- Sound like a person, not a marketing bot\n"
            "- Include a clear, low-pressure call to action\n"
            "- For email: include subject line\n"
            "- For LinkedIn/Twitter: keep it under 300 characters, conversational\n"
            "- For web form: polite, professional, concise\n"
            "Return ONLY valid JSON with keys: subject (optional for non-email), body."
        )

        deliverable_text = ""
        if deliverable_description:
            deliverable_text = (
                f"\nDELIVERABLE (attach or link this): {deliverable_description}\n"
            )

        contact_text = ""
        if contact_info:
            contact_text = (
                f"\nYOUR CONTACT:\n"
                f"Name: {contact_info.get('name', '')}\n"
                f"Email: {contact_info.get('email', '')}\n"
                f"Website: {contact_info.get('website', '')}\n"
                f"Phone: {contact_info.get('phone', '')}\n"
                f"Address: {contact_info.get('address', '')}\n"
            )

        user = (
            f"LEAD:\n{lead}\n\n"
            f"SELLER PROFILE:\n{profile_summary}\n\n"
            f"TONE:\n{ tone }\n\n"
            f"CHANNEL: {channel}\n"
            f"MODE: {mode}\n"
            f"{deliverable_text}"
            f"{contact_text}\n\n"
            "Write a humanized message. Return ONLY valid JSON."
        )
        text = self.complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
        )
        return self._parse_json(text)

    def humanize_check(
        self,
        message: str,
        avoid_patterns: list[str],
    ) -> dict[str, Any]:
        """Check if a message sounds human. Returns {human_score: 0-100, issues: [...], rewritten: str}."""
        system = (
            "You detect AI-generated writing patterns. Score the message 0-100 on how human it sounds "
            "(100 = completely human). Flag any AI clichés, overly formal structure, or robotic phrasing. "
            "If score < 70, provide a rewritten version that sounds like a real person. "
            "Return JSON: {human_score, issues, rewritten}."
        )
        user = f"MESSAGE:\n{message}\n\nAVOID PATTERNS: {avoid_patterns}\n\nReturn ONLY valid JSON."
        text = self.complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
        )
        return self._parse_json(text)

    def choose_deliverable(
        self,
        lead: dict[str, Any],
        profile_summary: str,
        deliverable_types: list[str],
    ) -> dict[str, Any]:
        """Choose which work-first deliverable fits this lead."""
        system = (
            "Choose the best work-first deliverable for this lead. "
            "Return JSON: {deliverable_type, description, reason}. "
            "Types: mockup (visual redesign), audit (performance/accessibility report), "
            "code_sample (small working widget)."
        )
        user = (
            f"LEAD:\n{lead}\n\nSELLER PROFILE:\n{profile_summary}\n\n"
            f"AVAILABLE TYPES: {deliverable_types}\nReturn ONLY valid JSON."
        )
        text = self.complete(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
        )
        return self._parse_json(text)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        import json
        import re

        # Try to extract JSON from markdown code blocks or plain text
        text = text.strip()
        # Remove markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
        # Find the first { ... } block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text, "parse_error": True}