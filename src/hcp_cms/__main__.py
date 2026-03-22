"""Allow running as `python -m hcp_cms`."""

from hcp_cms.app import main

raise SystemExit(main())
