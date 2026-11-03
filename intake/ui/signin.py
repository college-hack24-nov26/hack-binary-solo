"""Step 1: sign in (staff or doctor). Once signed in, main_app.py swaps this page for the rest of the flow."""
from intake.ui.gate import require_login

require_login()
