# video-making

`code/app.py`(슬라이드쇼)와 `code/subtitle_editor.py`(자막 편집기)를 각각 배포 가능한 실행파일로 빌드할 수 있습니다.

## 로컬 실행

```bash
uv run python code/app.py
uv run python code/subtitle_editor.py
```

## 배포 빌드 (PyInstaller)

중요: Windows 실행파일은 Windows에서, macOS 앱은 macOS에서 각각 빌드해야 합니다.

### Windows

```powershell
uv sync
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1 -Clean
```

출력:
- `dist/slideshow-app/`
- `dist/subtitle-editor/`

### macOS

```bash
uv sync
chmod +x ./scripts/build_macos.sh
./scripts/build_macos.sh --clean
```

출력:
- `dist/slideshow-app.app`
- `dist/subtitle-editor.app`

## 설정 파일 위치

앱 설정은 OS별 사용자 설정 경로에 저장됩니다.
- Windows: `%APPDATA%\video-making\settings.json`
- macOS: `~/Library/Application Support/video-making/settings.json`
- Linux: `$XDG_CONFIG_HOME/video-making/settings.json` (없으면 `~/.config/video-making/settings.json`)
