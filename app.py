# app.py
"""
Run the desktop app:
1) pip install -r requirements.txt
2) python app.py
"""
from settings_bootstrap import configure_django
configure_django()

import django
django.setup()

from orm_utils import migrate_if_needed, seed_initial_data
from ui import QuotationApp

if __name__ == "__main__":
    migrate_if_needed()
    seed_initial_data()
    app = QuotationApp()
    app.mainloop()
