"""Single source of truth for the in-app how-to guide.

Used by the Help page (via /api/help) AND injected into the AI assistant's
system prompt so it can guide users who get stuck.
"""
from __future__ import annotations

HELP_SECTIONS: dict[str, list[dict]] = {
    "en": [
        {"title": "Getting started", "items": [
            "Open the site and log in with the email and password your manager gave you.",
            "Switch language anytime with the ES / EN toggle (top right).",
            "On a phone you can install it: Share → Add to Home Screen (iPhone) or ⋮ → Install app (Android).",
            "Change your own password with the key icon next to Log out.",
        ]},
        {"title": "Roles", "items": [
            "Super Admin: manages all organizations and creates country managers.",
            "Country Manager: owns one organization — its regions, centers, people and inventory.",
            "Regional Manager: manages centers and people in their region.",
            "Center Manager: manages volunteers and inventory in their center.",
            "Volunteer: records stock in/out and counts at their center.",
            "Each organization is isolated — you only see your own organization's data.",
        ]},
        {"title": "Record stock in / out", "items": [
            "Inventory → Record movement, or the ↓ (in) / ↑ (out) buttons on an item.",
            "Choose Receiving (in) or Dispatching (out); enter item, quantity and unit.",
            "Add the supplier/donor (in) or recipient (out), and a reason.",
            "For food/medicine, add the expiry date and lot — dispatch uses First-Expired-First-Out automatically.",
        ]},
        {"title": "Find & manage items", "items": [
            "Search by name or barcode; turn on Smart search to find by meaning.",
            "Filter by All / Low stock / Expiring / Expired.",
            "New item: set unit, reorder level (minimum) and barcode; category is auto-detected.",
            "Open an item to see its batches and full history.",
        ]},
        {"title": "Fix mistakes", "items": [
            "Open an item → Edit to fix its name, unit, category, minimum or barcode.",
            "Correct stock: enter the correct quantity and it logs an adjustment.",
            "Undo (↩) on any movement reverses it and restores the exact lot/expiry; the original stays marked 'undone'.",
        ]},
        {"title": "Scan QR / barcodes", "items": [
            "Tap Scan (top bar) to open the camera on your phone.",
            "Scan a QR or barcode to instantly see the item and count it, or stock it in/out.",
            "Unknown codes can create a new item on the spot.",
            "Print QR labels and bin/stock cards from Inventory.",
        ]},
        {"title": "Import Excel", "items": [
            "Use 'Updated inventory (sync)' when re-uploading an updated sheet — it reconciles quantities instead of adding (no double counting).",
            "Use 'New arrivals (add)' when each row is a new donation.",
            "In sync mode you review and edit a reconciliation preview, then approve.",
            "Columns are mapped automatically, items classified, and duplicates merged.",
        ]},
        {"title": "Alerts & requests", "items": [
            "Alerts shows expired, expiring (≤30 days) and low/out-of-stock items; you can Dispose expired stock.",
            "Requests: log what the field needs with a priority; Fulfill dispatches it from stock.",
        ]},
        {"title": "AI assistant & voice", "items": [
            "Open the assistant and type or use the microphone (it understands Spanish and English).",
            "Examples: 'We received 200 boxes of rice from the Red Cross', 'Dispatch 50 water bottles', 'How much medicine do we have?', 'Fix rice to 45'.",
            "Everything the assistant does is recorded under your name.",
        ]},
        {"title": "Reports & history", "items": [
            "Dashboard → Report (PDF) creates a donor-ready summary you can save as PDF.",
            "Activity log shows everything that happened; the Corrections tab shows fixes and who made them.",
        ]},
        {"title": "Managing your organization", "items": [
            "Organization → People to add team members (roles below yours) and assign their region/center.",
            "Country managers create regions and centers; regional managers create centers.",
            "Super admins use Organizations → Add country manager (pick a country) to create a new organization.",
        ]},
    ],
    "es": [
        {"title": "Primeros pasos", "items": [
            "Abre el sitio e inicia sesión con el correo y la contraseña que te dio tu responsable.",
            "Cambia el idioma cuando quieras con el botón ES / EN (arriba a la derecha).",
            "En el celular puedes instalarla: Compartir → Agregar a inicio (iPhone) o ⋮ → Instalar app (Android).",
            "Cambia tu contraseña con el ícono de llave junto a Cerrar sesión.",
        ]},
        {"title": "Roles", "items": [
            "Super Administrador: administra todas las organizaciones y crea gerentes de país.",
            "Gerente de País: dueño de una organización — sus regiones, centros, personas e inventario.",
            "Gerente Regional: administra los centros y personas de su región.",
            "Gerente de Centro: administra voluntarios e inventario de su centro.",
            "Voluntario: registra entradas/salidas y conteos en su centro.",
            "Cada organización está aislada — solo ves los datos de tu organización.",
        ]},
        {"title": "Registrar entradas / salidas", "items": [
            "Inventario → Registrar movimiento, o las flechas ↓ (entra) / ↑ (sale) en cada artículo.",
            "Elige Recibiendo (entra) o Despachando (sale); pon artículo, cantidad y unidad.",
            "Agrega el proveedor/donante (entra) o el destinatario (sale), y un motivo.",
            "Para alimentos/medicinas pon vencimiento y lote — al despachar sale primero lo que vence antes (FEFO).",
        ]},
        {"title": "Buscar y gestionar artículos", "items": [
            "Busca por nombre o código de barras; activa Inteligente para buscar por significado.",
            "Filtra por Todos / Stock bajo / Por vencer / Vencidos.",
            "Nuevo artículo: define unidad, nivel mínimo (reorden) y código; la categoría se detecta sola.",
            "Abre un artículo para ver sus lotes y todo su historial.",
        ]},
        {"title": "Corregir errores", "items": [
            "Abre un artículo → Editar para corregir nombre, unidad, categoría, mínimo o código.",
            "Corregir stock: escribe la cantidad correcta y se registra el ajuste.",
            "Deshacer (↩) en un movimiento lo revierte y restaura el lote/vencimiento exactos; el original queda marcado como 'deshecho'.",
        ]},
        {"title": "Escanear QR / códigos de barras", "items": [
            "Pulsa Escanear (barra superior) para abrir la cámara del celular.",
            "Escanea un QR o código de barras para ver el artículo y contarlo, o registrar entrada/salida.",
            "Si el código no existe, puedes crear el artículo al momento.",
            "Imprime etiquetas QR y tarjetas de stock desde Inventario.",
        ]},
        {"title": "Importar Excel", "items": [
            "Usa 'Inventario actualizado (sincronizar)' al volver a subir una hoja actualizada — concilia cantidades en vez de sumar (sin duplicar).",
            "Usa 'Nuevas entradas (sumar)' cuando cada fila es una donación nueva.",
            "En modo sincronizar revisas y editas una vista previa de conciliación y luego apruebas.",
            "Las columnas se mapean solas, los artículos se clasifican y los duplicados se fusionan.",
        ]},
        {"title": "Alertas y solicitudes", "items": [
            "Alertas muestra vencidos, por vencer (≤30 días) y stock bajo/agotado; puedes Desechar lo vencido.",
            "Solicitudes: registra lo que el terreno necesita con prioridad; Cumplir lo despacha del stock.",
        ]},
        {"title": "Asistente con IA y voz", "items": [
            "Abre el asistente y escribe o usa el micrófono (entiende español e inglés).",
            "Ejemplos: 'Recibimos 200 cajas de arroz de Cruz Roja', 'Despacha 50 botellas de agua', '¿Cuánta medicina tenemos?', 'Corrige el arroz a 45'.",
            "Todo lo que hace el asistente queda registrado a tu nombre.",
        ]},
        {"title": "Reportes e historial", "items": [
            "Panel → Informe (PDF) genera un resumen para donantes que puedes guardar como PDF.",
            "El Registro de actividad muestra todo lo ocurrido; la pestaña Correcciones muestra los ajustes y quién los hizo.",
        ]},
        {"title": "Administrar tu organización", "items": [
            "Organización → Personas para agregar miembros (roles por debajo del tuyo) y asignar su región/centro.",
            "Los gerentes de país crean regiones y centros; los regionales crean centros.",
            "El super admin usa Organizaciones → Agregar gerente de país (elige un país) para crear una nueva organización.",
        ]},
    ],
}


def help_sections(lang: str) -> list[dict]:
    return HELP_SECTIONS.get(lang if lang in HELP_SECTIONS else "en")


def help_for_agent() -> str:
    """Compact how-to (English) injected into the assistant's system prompt."""
    lines = ["HOW TO USE ACOPIO (use this to guide users who ask how to do something):"]
    for sec in HELP_SECTIONS["en"]:
        lines.append(f"- {sec['title']}: " + " ".join(sec["items"]))
    return "\n".join(lines)
