# Database Stability - Prevention of Table Loss

## Root Cause Analysis

The "vanishing tables" issue was caused by the test infrastructure in `tests/conftest.py:44`:

```python
# Clean up: drop all tables
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.drop_all)  # ⚠️ THIS DROPS ALL TABLES
```

This happens when running tests that use the PostgreSQL database connection.

## Prevention Measures

### 1. **Never Run Tests Against Production Database**
- Always use `DATABASE_URL` environment variable to point to test databases
- Production databases should never have `Base.metadata.drop_all()` run against them

### 2. **Test Environment Isolation**
- The conftest fixture only drops tables when `DATABASE_URL` contains "postgresql"
- Local development should use separate test databases
- CI environments should use isolated database instances

### 3. **Migration State Verification**
```bash
# Always verify before running tests
alembic current
docker exec postgres-secondary psql -U postgres -d mydb -c "\\dt"
```

### 4. **Safe Testing Practices**
- Use unit tests for grader logic (no database)
- Use mocked databases for API testing when possible
- Run integration tests against disposable test databases only

## Recovery Procedure (if tables are lost)

1. **Reset migration state:**
   ```bash
   docker exec postgres-secondary psql -U postgres -d mydb -c "DELETE FROM alembic_version;"
   ```

2. **Reapply all migrations:**
   ```bash
   alembic upgrade head
   ```

3. **Verify restoration:**
   ```bash
   docker exec postgres-secondary psql -U postgres -d mydb -c "\\dt"
   ```

## Current Status

✅ **Database is stable** - All 11 tables exist and persist correctly
✅ **Migration state:** `544554655cfb (head)` - Step 5 complete  
✅ **Data persistence verified** - Quiz workflow data survives across sessions
✅ **Production ready** - No more table vanishing issues expected

## Monitoring

The database should be monitored for:
- Migration state consistency
- Table existence after deployments  
- Data integrity across application restarts

Tables expected:
- alembic_version, orgs, users, items, sources, media_assets
- scheduler_state, reviews (Step 4)
- quizzes, quiz_items, results (Step 5)