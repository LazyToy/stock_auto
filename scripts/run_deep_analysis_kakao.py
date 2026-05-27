from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


DEFAULT_OUTPUT_DIR = Path("reports") / "deep_analysis"
DEFAULT_MAX_MESSAGE_CHARS = 180
logger = logging.getLogger(__name__)


class StockAnalyst(Protocol):
    def analyze_stock(self, symbol: str) -> dict[str, Any]:
        """Return a deep-analysis payload for a symbol."""


class MessageNotifier(Protocol):
    def send_message(self, message: str) -> bool:
        """Send a plain text message."""


def run_deep_analysis_kakao(
    symbol: str,
    *,
    analyst: StockAnalyst | None = None,
    notifier: MessageNotifier | Any | None = None,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    generated_at: datetime | None = None,
    max_message_chars: int = DEFAULT_MAX_MESSAGE_CHARS,
    send: bool = True,
) -> dict[str, Any]:
    normalized_symbol = _normalize_symbol(symbol)
    generated_time = generated_at or datetime.now()
    active_analyst = analyst or _build_default_analyst()

    analysis = active_analyst.analyze_stock(normalized_symbol)
    report_path = save_deep_analysis_report(
        normalized_symbol,
        analysis,
        output_dir=output_dir,
        generated_at=generated_time,
    )
    message = format_deep_analysis_message(
        normalized_symbol,
        analysis,
        generated_at=generated_time,
        report_path=report_path,
    )
    messages = split_message(message, max_chars=max_message_chars)

    sent = False
    errors: list[str] = []
    if send:
        active_notifier = notifier or _build_default_notifier()
        sent_results: list[bool] = []
        for chunk in messages:
            chunk_sent, error = _send_message(active_notifier, chunk)
            sent_results.append(chunk_sent)
            if error:
                errors.append(error)
            elif not chunk_sent:
                errors.append("provider_returned_false")
        sent = all(sent_results)

    return {
        "symbol": normalized_symbol,
        "analysis": analysis,
        "report_path": str(report_path),
        "message_count": len(messages),
        "sent": sent,
        "errors": errors,
        "messages": messages,
    }


def format_deep_analysis_message(
    symbol: str,
    analysis: dict[str, Any],
    *,
    generated_at: datetime,
    report_path: Path | str | None = None,
) -> str:
    signal = _string_value(analysis.get("signal"), "UNKNOWN").upper()
    confidence = _format_confidence(analysis.get("confidence"))
    reason = _truncate(_string_value(analysis.get("reason"), "No reason returned."), 220)
    sources = _coerce_strings(analysis.get("analysis_sources"))[:4]
    key_drivers = _coerce_strings(analysis.get("key_drivers"))[:3]
    risk_factors = _coerce_strings(analysis.get("risk_factors"))[:3]

    lines = [
        "[Deep Analysis]",
        f"Symbol: {symbol}",
        f"Signal: {signal}",
        f"Confidence: {confidence}",
        f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M')}",
    ]
    if sources:
        lines.append("Sources: " + ", ".join(sources))
    lines.extend(["", "Reason:", reason])
    lines.extend(_format_numbered_section("Key drivers", key_drivers))
    lines.extend(_format_numbered_section("Risks", risk_factors))
    if report_path is not None:
        lines.extend(["", f"Full report: {Path(report_path).as_posix()}"])
    lines.extend(["", "Note: advisory only; no auto-order was placed."])
    return "\n".join(lines)


def save_deep_analysis_report(
    symbol: str,
    analysis: dict[str, Any],
    *,
    output_dir: Path | str,
    generated_at: datetime,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    timestamp = generated_at.strftime("%Y%m%d_%H%M%S")
    report_path = _unique_path(output_path / f"{symbol}_deep_analysis_{timestamp}.json")
    payload = {
        "symbol": symbol,
        "generated_at": generated_at.isoformat(),
        "analysis": analysis,
    }
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report_path


def split_message(message: str, *, max_chars: int = DEFAULT_MAX_MESSAGE_CHARS) -> list[str]:
    if max_chars < 80:
        raise ValueError("max_chars must be at least 80")
    if len(message) <= max_chars:
        return [message]

    body_limit = max_chars - 12
    chunks = _split_body(message, body_limit)
    total = len(chunks)
    prefix_len = len(f"[{total}/{total}]\n")
    body_limit = max_chars - prefix_len
    chunks = _split_body(message, body_limit)
    total = len(chunks)
    return [f"[{index}/{total}]\n{chunk}" for index, chunk in enumerate(chunks, start=1)]


def _split_body(message: str, body_limit: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in message.splitlines():
        pending = line
        while len(pending) > body_limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            chunks.append(pending[:body_limit])
            pending = pending[body_limit:]

        candidate = pending if not current else f"{current}\n{pending}"
        if len(candidate) <= body_limit:
            current = candidate
        else:
            chunks.append(current.rstrip())
            current = pending

    if current:
        chunks.append(current.rstrip())
    return chunks


def _send_message(provider: Any, message: str) -> tuple[bool, str | None]:
    try:
        if callable(provider) and not hasattr(provider, "send_message"):
            return bool(provider(message)), None
        return bool(provider.send_message(message)), None
    except Exception as exc:
        redacted = _redact_sensitive_text(exc)
        logger.warning("Deep analysis notification failed: %s", redacted)
        return False, redacted


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _redact_sensitive_text(value: object) -> str:
    text = str(value)
    text = re.sub(r"Bearer\s+[A-Za-z0-9._~+\-/:=]+", "Bearer <redacted>", text)
    text = re.sub(r"bot[^/\s]+/sendMessage", "bot<redacted>/sendMessage", text)
    text = re.sub(
        r"https://discord(?:app)?\.com/api/webhooks/[^\s]+",
        "https://discord.com/api/webhooks/<redacted>",
        text,
    )
    text = re.sub(r"(?i)(access_token|refresh_token|client_secret)=([^\s&]+)", r"\1=<redacted>", text)
    return text


def _format_numbered_section(title: str, values: list[str]) -> list[str]:
    lines = ["", f"{title}:"]
    if not values:
        lines.append("- N/A")
    else:
        lines.extend(f"{index}. {_truncate(value, 160)}" for index, value in enumerate(values, start=1))
    return lines


def _coerce_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _format_confidence(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if 0.0 <= numeric <= 1.0:
        return f"{numeric:.0%}"
    return f"{numeric:.2f}"


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _string_value(value: Any, default: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def _normalize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    return symbol.strip().upper()


def _build_default_analyst() -> StockAnalyst:
    from src.analysis.multimodal import MultimodalAnalyst

    return MultimodalAnalyst()


def _build_default_notifier() -> MessageNotifier:
    from src.utils.kakao_notifier import get_kakao_notifier

    return get_kakao_notifier()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deep stock analysis and send a Kakao summary.")
    parser.add_argument("symbol", help="Stock symbol, for example 0183J0 or AAPL")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-message-chars", type=int, default=DEFAULT_MAX_MESSAGE_CHARS)
    parser.add_argument("--no-send", action="store_true", help="Save the report without sending Kakao.")
    args = parser.parse_args(argv)

    try:
        result = run_deep_analysis_kakao(
            args.symbol,
            output_dir=args.output_dir,
            max_message_chars=args.max_message_chars,
            send=not args.no_send,
        )
    except Exception as exc:
        print(f"Deep analysis failed: {exc}", file=sys.stderr)
        return 1

    print(f"Report: {result['report_path']}")
    print(f"Messages: {result['message_count']}")
    print(f"Kakao sent: {result['sent']}")
    return 0 if (args.no_send or result["sent"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
