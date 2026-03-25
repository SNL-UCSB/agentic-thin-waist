from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BrowserViewport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int
    height: int


class BrowserFindTextResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    count: int
    visible: bool
    matches: tuple[str, ...] = ()


class BrowserDropdownOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: str
    selected: bool = False
    disabled: bool = False


class StealthProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_agent: str | None = None
    locale: str | None = None
    timezone_id: str | None = None
    platform: str | None = None
    languages: tuple[str, ...] = ("en-US", "en")
    vendor: str = "Google Inc."
    webgl_vendor: str = "Google Inc. (Intel)"
    webgl_renderer: str = "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics, D3D11)"
    extra_http_headers: dict[str, str] = Field(default_factory=dict)
    viewport: BrowserViewport | None = None
    mask_webdriver: bool = True
    patch_chrome_runtime: bool = True
    patch_plugins: bool = True
    patch_permissions: bool = True

    def context_kwargs(self) -> dict[str, Any]:
        context_kwargs: dict[str, Any] = {}
        if self.user_agent is not None:
            context_kwargs["user_agent"] = self.user_agent
        if self.locale is not None:
            context_kwargs["locale"] = self.locale
        if self.timezone_id is not None:
            context_kwargs["timezone_id"] = self.timezone_id
        if self.viewport is not None:
            context_kwargs["viewport"] = self.viewport.model_dump()
        if self.extra_http_headers:
            context_kwargs["extra_http_headers"] = self.extra_http_headers
        return context_kwargs

    def init_scripts(self) -> list[str]:
        languages = ", ".join(repr(language) for language in self.languages)
        scripts: list[str] = []

        if self.mask_webdriver:
            scripts.append(
                """
                Object.defineProperty(navigator, 'webdriver', {
                  get: () => undefined
                });
                """
            )

        scripts.append(
            f"""
            Object.defineProperty(navigator, 'languages', {{
              get: () => [{languages}]
            }});
            """
        )

        if self.platform is not None:
            scripts.append(
                f"""
                Object.defineProperty(navigator, 'platform', {{
                  get: () => {self.platform!r}
                }});
                """
            )

        scripts.append(
            f"""
            Object.defineProperty(navigator, 'vendor', {{
              get: () => {self.vendor!r}
            }});
            """
        )

        if self.patch_chrome_runtime:
            scripts.append(
                """
                if (!window.chrome) {
                  Object.defineProperty(window, 'chrome', {
                    value: { runtime: {} },
                    configurable: true
                  });
                } else if (!window.chrome.runtime) {
                  Object.defineProperty(window.chrome, 'runtime', {
                    value: {},
                    configurable: true
                  });
                }
                """
            )

        if self.patch_plugins:
            scripts.append(
                """
                const fakePlugins = [
                  { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                  { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                  { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                ];
                Object.defineProperty(navigator, 'plugins', {
                  get: () => fakePlugins
                });
                Object.defineProperty(navigator, 'mimeTypes', {
                  get: () => [
                    { type: 'application/pdf', suffixes: 'pdf', description: '', enabledPlugin: fakePlugins[0] }
                  ]
                });
                """
            )

        if self.patch_permissions:
            scripts.append(
                """
                const originalQuery = window.navigator.permissions?.query?.bind(window.navigator.permissions);
                if (originalQuery) {
                  window.navigator.permissions.query = (parameters) => (
                    parameters && parameters.name === 'notifications'
                      ? Promise.resolve({ state: Notification.permission })
                      : originalQuery(parameters)
                  );
                }
                """
            )

        scripts.append(
            f"""
            const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {{
              if (parameter === 37445) return {self.webgl_vendor!r};
              if (parameter === 37446) return {self.webgl_renderer!r};
              return originalGetParameter.call(this, parameter);
            }};
            """
        )

        return [self._wrap_script(script) for script in scripts]

    @staticmethod
    def _wrap_script(script: str) -> str:
        return f"(() => {{ {script} }})();"
