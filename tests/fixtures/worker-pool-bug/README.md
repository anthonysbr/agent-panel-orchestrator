# worker-pool-bug fixture

Known bug: `WorkerPool.process` returns an inflated processed count.

Expected fix: copy from `expected/pool.py` over `worker_pool/pool.py`.

Gates: compileall + unittest in this mini-repo.
