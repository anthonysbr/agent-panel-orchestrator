# api-monolith fixture

Security debt: raw SQL string interpolation in `app/handlers.py`.

Fix: use parameterized-style builder from `expected/handlers.py`.
