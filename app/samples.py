"""Mark processed decks as demo samples. Run from the project folder:

    python -m app.samples list
    python -m app.samples add <document id>
    python -m app.samples remove <document id>

<document id> is the id in the web address: http://localhost:5173/documents/<document id>.
Local and deployed servers use the same TiDB, so a sample added here appears on the live
site too. Samples can't be re-processed: to update one, remove it, click "Find problems
again" in the web app, then add it again.
"""

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine
from app.models import Document
from app.pdf_store import is_stored


def list_documents(db: Session) -> None:
    for document in db.scalars(select(Document).order_by(Document.id)).all():
        mark = "SAMPLE" if document.is_sample else "      "
        print(f"{mark}  {document.public_id}  {document.status:<9}  {document.filename}")


def set_sample(db: Session, public_id: str, is_sample: bool) -> int:
    document = db.scalar(select(Document).where(Document.public_id == public_id))
    if document is None:
        print("No document with that id. Run 'python -m app.samples list' to see the ids.")
        return 1
    if is_sample and document.status != "processed":
        print("This deck isn't processed yet. Process it in the web app first.")
        return 1
    if is_sample and not is_stored(db, document):
        print("This deck's PDF isn't stored in TiDB yet. Start the backend once, then try again.")
        return 1
    document.is_sample = is_sample
    db.commit()
    print(f"{'Added' if is_sample else 'Removed'} sample: {document.filename}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark processed decks as demo samples.")
    parser.add_argument("action", choices=["list", "add", "remove"])
    parser.add_argument("document_id", nargs="?", help="the id from the web address")
    args = parser.parse_args()

    with Session(engine) as db:
        if args.action == "list":
            list_documents(db)
            return 0
        if not args.document_id:
            parser.error("add and remove need a document id")
        return set_sample(db, args.document_id, is_sample=(args.action == "add"))


if __name__ == "__main__":
    sys.exit(main())
