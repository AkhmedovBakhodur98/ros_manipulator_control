"""Medicine database management.

Usage:
    # Add medicine interactively
    python db_manager.py add --name "Аспирин Кардио" --image photo.jpg

    # List all medicines
    python db_manager.py list

    # Search by text
    python db_manager.py search --text "аспирин"

    # Remove medicine
    python db_manager.py remove --id MED-00001
"""

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "db" / "medicines.db"
REF_DIR = Path(__file__).resolve().parent / "db" / "reference_images"

SCHEMA = """
CREATE TABLE IF NOT EXISTS medicines (
    medicine_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    aliases       TEXT DEFAULT '',
    reference_image TEXT,
    barcode       TEXT DEFAULT '',
    description   TEXT DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
"""


def get_db():
    """Open database, create schema if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def normalize(text):
    """Normalize text for fuzzy matching."""
    return text.lower().strip()


def next_id(conn):
    """Generate next medicine ID."""
    row = conn.execute("SELECT COUNT(*) as cnt FROM medicines").fetchone()
    return f"MED-{row['cnt'] + 1:05d}"


def add_medicine(args):
    conn = get_db()
    med_id = next_id(conn)
    now = datetime.now().isoformat()

    # Copy reference image
    ref_image_path = None
    if args.image:
        REF_DIR.mkdir(parents=True, exist_ok=True)
        src = Path(args.image)
        dst = REF_DIR / f"{med_id}{src.suffix}"
        shutil.copy2(src, dst)
        ref_image_path = dst.name

    conn.execute(
        """INSERT INTO medicines
           (medicine_id, name, name_normalized, aliases, reference_image,
            barcode, description, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (med_id, args.name, normalize(args.name),
         args.aliases or "", ref_image_path,
         args.barcode or "", args.description or "",
         now, now)
    )
    conn.commit()
    print(f"Added: {med_id} — {args.name}")
    if ref_image_path:
        print(f"  Reference image: db/reference_images/{ref_image_path}")
    conn.close()


def list_medicines(args):
    conn = get_db()
    rows = conn.execute("SELECT * FROM medicines ORDER BY medicine_id").fetchall()
    if not rows:
        print("Database is empty")
        return
    print(f"{'ID':<12} {'Name':<30} {'Barcode':<15} {'Image'}")
    print("-" * 75)
    for row in rows:
        img = row["reference_image"] or "-"
        barcode = row["barcode"] or "-"
        print(f"{row['medicine_id']:<12} {row['name']:<30} {barcode:<15} {img}")
    print(f"\nTotal: {len(rows)} medicines")
    conn.close()


def search_medicines(args):
    conn = get_db()
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        print("Install rapidfuzz: pip install rapidfuzz")
        return

    rows = conn.execute("SELECT medicine_id, name, name_normalized FROM medicines").fetchall()
    if not rows:
        print("Database is empty")
        return

    choices = {row["medicine_id"]: row["name_normalized"] for row in rows}
    matches = process.extract(
        normalize(args.text), choices,
        scorer=fuzz.token_sort_ratio,
        limit=5
    )

    print(f"Search: '{args.text}'")
    print(f"{'Score':<8} {'ID':<12} {'Name'}")
    print("-" * 50)
    for name_norm, score, med_id in matches:
        # Get full name
        row = conn.execute(
            "SELECT name FROM medicines WHERE medicine_id = ?", (med_id,)
        ).fetchone()
        print(f"{score:<8.1f} {med_id:<12} {row['name']}")
    conn.close()


def remove_medicine(args):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM medicines WHERE medicine_id = ?", (args.id,)
    ).fetchone()
    if not row:
        print(f"Not found: {args.id}")
        return

    # Remove reference image
    if row["reference_image"]:
        img_path = REF_DIR / row["reference_image"]
        if img_path.exists():
            img_path.unlink()

    conn.execute("DELETE FROM medicines WHERE medicine_id = ?", (args.id,))
    conn.commit()
    print(f"Removed: {args.id} — {row['name']}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Medicine database manager")
    sub = parser.add_subparsers(dest="command")

    p_add = sub.add_parser("add", help="Add medicine to database")
    p_add.add_argument("--name", required=True, help="Medicine name")
    p_add.add_argument("--image", help="Reference image path")
    p_add.add_argument("--aliases", help="Comma-separated aliases")
    p_add.add_argument("--barcode", help="Barcode string")
    p_add.add_argument("--description", help="Description")

    sub.add_parser("list", help="List all medicines")

    p_search = sub.add_parser("search", help="Search by text")
    p_search.add_argument("--text", required=True, help="Search text")

    p_remove = sub.add_parser("remove", help="Remove medicine")
    p_remove.add_argument("--id", required=True, help="Medicine ID")

    args = parser.parse_args()

    if args.command == "add":
        add_medicine(args)
    elif args.command == "list":
        list_medicines(args)
    elif args.command == "search":
        search_medicines(args)
    elif args.command == "remove":
        remove_medicine(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
