"""Start the development server: ``python run.py``  (http://127.0.0.1:5000)."""

import os
import sys

from orbit import create_app
from orbit.database import ensure_ready
from orbit.errors import DatabaseNotReady

app = create_app()


def main() -> int:
    with app.app_context():
        try:
            ensure_ready()
        except DatabaseNotReady as error:
            print(f'Cannot start: {error}', file=sys.stderr)
            return 1
    app.run(
        host=os.environ.get('HOST', '127.0.0.1'), port=int(os.environ.get('PORT', '5000')), debug=app.config['DEBUG']
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
