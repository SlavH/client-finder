"""Work-first deliverable generation for outreach.

Creates tangible deliverables (mockups, audits, code samples) that are
attached or linked in outreach messages to increase response rates.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from client_finder.llm import LLMClient


class DeliverableGenerator:
    def __init__(self, config: dict[str, Any], llm: LLMClient, output_dir: str = "work/"):
        self.config = config
        self.llm = llm
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        lead_id: str,
        company: str,
        pain_point: str,
        website: str | None,
        url: str | None,
        profile_summary: str,
        deliverable_type: str,
    ) -> dict[str, Any]:
        """Generate a deliverable for a lead. Returns {type, path, description, html}."""
        lead_dir = self.output_dir / lead_id
        lead_dir.mkdir(parents=True, exist_ok=True)

        if deliverable_type == "mockup":
            return self._generate_mockup(lead_dir, company, pain_point, website, url, profile_summary)
        if deliverable_type == "audit":
            return self._generate_audit(lead_dir, company, website, url)
        if deliverable_type == "code_sample":
            return self._generate_code_sample(lead_dir, company, pain_point, profile_summary)
        return {"type": deliverable_type, "path": None, "error": "unknown type"}

    def _generate_mockup(
        self,
        lead_dir: Path,
        company: str,
        pain_point: str,
        website: str | None,
        url: str | None,
        profile_summary: str,
    ) -> dict[str, Any]:
        """Generate a single-page HTML/CSS redesign mockup."""
        prompt = (
            f"Create a complete, single-file HTML mockup (HTML + embedded CSS) for a redesigned homepage "
            f"for '{company}'. Their pain point is: {pain_point}.\n"
            f"Current website: {website or url or 'unknown'}\n"
            f"Seller profile: {profile_summary}\n\n"
            "Requirements:\n"
            "- Single HTML file with embedded <style> CSS\n"
            "- Modern, clean, mobile-responsive design\n"
            "- Hero section, value proposition, services, contact section\n"
            "- No external dependencies (no CDN, no frameworks)\n"
            "- Include a placeholder for seller's contact info\n"
            "Return ONLY the complete HTML file content inside ```html ``` blocks."
        )
        result = self.llm.complete(
            [
                {"role": "system", "content": "You are a senior frontend developer."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=3000,
        )

        html = self._extract_code_block(result, "html")
        if not html:
            html = result

        path = lead_dir / "mockup.html"
        path.write_text(html, encoding="utf-8")

        return {
            "type": "mockup",
            "path": str(path),
            "description": f"Homepage redesign mockup for {company}",
            "html": html,
        }

    def _generate_audit(
        self,
        lead_dir: Path,
        company: str,
        website: str | None,
        url: str | None,
    ) -> dict[str, Any]:
        """Generate a performance/accessibility audit using Lighthouse if available."""
        target = website or url or ""
        audit_path = lead_dir / "audit.md"

        if not target:
            content = f"# Website Audit for {company}\n\nNo website URL provided for audit."
            audit_path.write_text(content, encoding="utf-8")
            return {"type": "audit", "path": str(audit_path), "description": f"Basic audit notes for {company}"}

        # Try Lighthouse CLI
        lighthouse_output = self._run_lighthouse(target)
        if lighthouse_output:
            content = f"# Website Performance Audit: {company}\n\nTarget: {target}\n\n{lighthouse_output}"
        else:
            content = (
                f"# Website Audit: {company}\n\nTarget: {target}\n\n"
                "Lighthouse CLI not available. Run `npx lighthouse {target}` manually.\n"
            )

        audit_path.write_text(content, encoding="utf-8")
        return {
            "type": "audit",
            "path": str(audit_path),
            "description": f"Performance & accessibility audit for {company}",
        }

    def _run_lighthouse(self, url: str) -> str | None:
        """Run Lighthouse CLI if available."""
        try:
            result = subprocess.run(
                ["npx", "lighthouse", url, "--quiet", "--output=json"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                categories = data.get("categories", {})
                lines = []
                for cat_name, cat_data in categories.items():
                    score = cat_data.get("score", 0)
                    if score is not None:
                        lines.append(f"- {cat_name}: {score:.0%}")
                if lines:
                    return "Lighthouse scores:\n" + "\n".join(lines)
        except Exception:
            pass
        return None

    def _generate_code_sample(
        self,
        lead_dir: Path,
        company: str,
        pain_point: str,
        profile_summary: str,
    ) -> dict[str, Any]:
        """Generate a small working code sample relevant to the lead's pain point."""
        prompt = (
            f"Write a small, self-contained code sample (HTML/JS or Python) that addresses this pain point "
            f"for '{company}': {pain_point}\n"
            f"Seller profile: {profile_summary}\n\n"
            "Requirements:\n"
            "- Single file, no external dependencies\n"
            "- Copy-paste ready and works immediately\n"
            "- Relevant to web development / automation\n"
            "- Include comments explaining what it does\n"
            "Return ONLY the code inside ```python ``` or ```html ``` blocks."
        )
        result = self.llm.complete(
            [
                {"role": "system", "content": "You are a senior software engineer."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        code = self._extract_code_block(result, "python") or self._extract_code_block(result, "html") or result
        ext = ".py" if "python" in result.lower()[:100] else ".html"
        path = lead_dir / f"code_sample{ext}"
        path.write_text(code, encoding="utf-8")

        return {
            "type": "code_sample",
            "path": str(path),
            "description": f"Working code sample for {company}'s {pain_point}",
        }

    @staticmethod
    def _extract_code_block(text: str, lang: str) -> str | None:
        import re
        pattern = rf"```{lang}\s*\n(.*?)\n```"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else None