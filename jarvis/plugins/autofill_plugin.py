
from loguru import logger
from jarvis.plugins.base import Plugin
from jarvis.models import ToolDefinition

_AUTOFILL_JS = """(profile) => {
  const groups = [
    ['email', ['email','e-mail']],
    ['phone', ['phone','tel','mobile','cell']],
    ['first_name', ['first name','firstname','fname','given-name','given name']],
    ['last_name', ['last name','lastname','lname','surname','family-name','family name']],
    ['username', ['username','user name','userid','login']],
    ['company', ['company','organization','organisation','employer']],
    ['job_title', ['job title','position','occupation']],
    ['address2', ['address 2','address-line2','addressline2','apt','apartment','suite','unit']],
    ['address', ['address','street','address-line1','addr']],
    ['city', ['city','town','locality']],
    ['state', ['state','province','region']],
    ['zip', ['zip','postal','postcode','postal code']],
    ['country', ['country']],
    ['url', ['website','homepage','url']],
    ['full_name', ['full name','your name','name']],
  ];
  const skip = new Set(['password','hidden','submit','button','checkbox','radio','file','image','reset','range','color']);
  const out = [];
  document.querySelectorAll('input, textarea, select').forEach(el => {
    const type = (el.type || 'text').toLowerCase();
    if (skip.has(type) || el.disabled || el.readOnly) return;
    let label = '';
    if (el.labels && el.labels[0]) label = el.labels[0].textContent;
    const hay = [el.getAttribute('autocomplete'), el.name, el.id, el.placeholder,
                 el.getAttribute('aria-label'), label].filter(Boolean).join(' ').toLowerCase();
    if (!hay) return;
    for (const [key, kws] of groups) {
      if (profile[key] == null || profile[key] === '') continue;
      if (!kws.some(k => hay.includes(k))) continue;
      const val = String(profile[key]);
      if (el.tagName.toLowerCase() === 'select') {
        let matched = false;
        for (const opt of el.options) {
          if (opt.value.toLowerCase() === val.toLowerCase() ||
              opt.textContent.trim().toLowerCase() === val.toLowerCase()) {
            el.value = opt.value; matched = true; break;
          }
        }
        if (!matched) continue;
      } else {
        try { el.focus(); } catch (e) {}
        el.value = val;
      }
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
      out.push({key: key, field: hay.substring(0, 40)});
      break;
    }
  });
  return out;
}"""


class AutofillPlugin(Plugin):
    """Smart form autofill. Save a profile (name, email, address, ...) once, then
    fill the form on the current managed-browser page in one shot."""

    def __init__(self):
        super().__init__("autofill")
        self._store = None

    def _get(self):
        if self._store is None:
            from jarvis.brain.profile_store import get_profile_store
            self._store = get_profile_store()
        return self._store

    async def initialize(self) -> None:
        logger.info("AutofillPlugin ready")

    async def shutdown(self) -> None:
        pass

    def get_tools(self):
        return [
            (
                ToolDefinition(
                    name="set_profile_field",
                    description=(
                        "Save a personal detail for form autofill (name, email, "
                        "phone, address, city, state, zip, country, company, etc.). "
                        "Use when the user says 'remember my email is ...', "
                        "'set my address to ...', 'my phone number is ...'."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "field": {"type": "string", "description": "e.g. email, phone, first_name, address, city, zip"},
                            "value": {"type": "string", "description": "The value to store"},
                        },
                        "required": ["field", "value"],
                    },
                ),
                self.set_profile_field,
            ),
            (
                ToolDefinition(
                    name="get_profile",
                    description="Show the saved autofill profile fields.",
                    parameters={"type": "object", "properties": {}},
                ),
                self.get_profile,
            ),
            (
                ToolDefinition(
                    name="autofill_form",
                    description=(
                        "Fill the form on the current managed-browser page using the "
                        "saved profile. Navigate to the page with a form first. Use "
                        "when the user says 'fill out this form', 'autofill this', "
                        "'enter my details'."
                    ),
                    parameters={"type": "object", "properties": {}},
                ),
                self.autofill_form,
            ),
            (
                ToolDefinition(
                    name="clear_profile_field",
                    description="Remove a saved profile field by name.",
                    parameters={
                        "type": "object",
                        "properties": {"field": {"type": "string"}},
                        "required": ["field"],
                    },
                ),
                self.clear_profile_field,
            ),
        ]

    async def set_profile_field(self, field: str, value: str) -> str:
        ck = self._get().set_field(field, value)
        return f"Saved '{ck}' for autofill."

    async def get_profile(self, **_) -> str:
        data = self._get().get_all()
        if not data:
            return "No autofill profile saved yet. Use set_profile_field to add details."
        lines = ["Autofill profile:"]
        for k, v in data.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    async def clear_profile_field(self, field: str) -> str:
        ok = self._get().clear_field(field)
        return f"Removed '{field}'." if ok else f"No saved field '{field}'."

    async def autofill_form(self, **_) -> str:
        from jarvis.app import get_runtime
        runtime = get_runtime()
        services = getattr(runtime, "services", None) if runtime else None
        browser = services.get("browser") if services else None
        if browser is None:
            return "Browser is not available."
        profile = self._get().get_all()
        if not profile:
            return "Your autofill profile is empty. Use set_profile_field first."
        try:
            await browser.initialize()
            page = getattr(browser, "_page", None)
            if page is None:
                return "No managed browser page is open. Navigate to a form first."
            filled = await page.evaluate(_AUTOFILL_JS, profile)
        except Exception as e:
            return f"Autofill failed: {e}"
        if not filled:
            return "No matching form fields found on this page."
        names = ", ".join(sorted({f["key"] for f in filled}))
        return f"Filled {len(filled)} field(s): {names}."
