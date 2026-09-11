"""캐릭터 표시 창.

characters/<name>/avatar.png 가 있으면 그 이미지를, 없으면 아래 기본 캐릭터를 보여준다.
기본 캐릭터는 외부 파일 없이 SVG + CSS만으로 움직여서, 이미지 생성 단계 전까지 자리를 지킨다.
"""
from __future__ import annotations

import base64

from core import characters

CSS = """
.avatar-stage {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 6px; padding: 10px 0 4px;
}
.avatar-stage img { max-height: 150px; border-radius: 12px; }
.avatar-bob { animation: avatar-bob 2.6s ease-in-out infinite; transform-origin: 50% 100%; }
@keyframes avatar-bob {
  0%, 100% { transform: translateY(0) rotate(-1.5deg); }
  50%      { transform: translateY(-9px) rotate(1.5deg); }
}
.avatar-blink { animation: avatar-blink 4.2s infinite; transform-origin: center; }
@keyframes avatar-blink {
  0%, 92%, 100% { transform: scaleY(1); }
  95%           { transform: scaleY(0.08); }
}
.avatar-name { font-weight: 600; opacity: 0.85; }
"""

_DEFAULT_SVG = """
<svg class="avatar-bob" width="140" height="140" viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg">
  <ellipse cx="60" cy="112" rx="26" ry="5" fill="rgba(0,0,0,0.14)"/>
  <path d="M60 16c22 0 36 16 36 38 0 24-16 42-36 42S24 78 24 54c0-22 14-38 36-38z" fill="#8ab4f8"/>
  <path d="M60 16c-22 0-36 16-36 38 0 8 2 15 5 21 4-30 18-46 43-50-4-6-8-9-12-9z" fill="#a9c8fb"/>
  <g class="avatar-blink">
    <circle cx="47" cy="56" r="5.5" fill="#1b2a44"/>
    <circle cx="73" cy="56" r="5.5" fill="#1b2a44"/>
    <circle cx="49" cy="54" r="1.8" fill="#fff"/>
    <circle cx="75" cy="54" r="1.8" fill="#fff"/>
  </g>
  <path d="M52 72q8 7 16 0" stroke="#1b2a44" stroke-width="3" fill="none" stroke-linecap="round"/>
  <circle cx="38" cy="66" r="4.5" fill="#f6a9b8" opacity="0.7"/>
  <circle cx="82" cy="66" r="4.5" fill="#f6a9b8" opacity="0.7"/>
</svg>
"""


def render(character: str) -> str:
    label = characters.load_display_name(character)
    image = characters.avatar_path(character)

    if image:
        data = base64.b64encode(image.read_bytes()).decode()
        mime = "image/gif" if image.suffix == ".gif" else "image/png"
        inner = f'<img class="avatar-bob" src="data:{mime};base64,{data}" alt="{label}">'
    else:
        inner = _DEFAULT_SVG

    return f'<div class="avatar-stage">{inner}<div class="avatar-name">{label}</div></div>'
