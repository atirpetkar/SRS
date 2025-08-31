# Progress Analytics Design Decisions

## Raw SQL vs SQLAlchemy ORM Choice

### Decision: Use Raw SQL for Progress Analytics

After comprehensive analysis of SQLAlchemy 2.x capabilities and long-term design considerations, we chose to use **raw SQL for progress analytics endpoints** while maintaining **ORM for all CRUD operations**.

### Rationale

#### 1. PostgreSQL-Specific Features
- **Array Operations**: `unnest(i.tags)` for tag analysis cannot be ported to ORM
- **Date/Time Functions**: `DATE(ts AT TIME ZONE 'UTC')` are database-specific
- **Schema Commitment**: Already using `ARRAY(Text)` columns, indicating PostgreSQL commitment

#### 2. Analytics vs CRUD Distinction
- **Steps 1-5 (CRUD)**: SQLAlchemy ORM ✅ - Perfect for business logic operations
- **Step 6 (Analytics)**: Raw SQL ✅ - Appropriate for read-only reporting queries
- **Different Requirements**: Analytics need performance optimization, CRUD needs maintainability

#### 3. Performance & Complexity
- **Direct Control**: Raw SQL allows fine-tuned query optimization for <1s response time target
- **Clarity**: Complex aggregations with CTEs and window functions more readable in SQL
- **DBA Optimization**: Database experts can optimize without code changes

#### 4. Industry Best Practices (2024-2025)
- **Hybrid Approach**: "Use SQLAlchemy for routine operations, raw SQL for performance-critical analytics"
- **Right Tool**: Analytics queries are fundamentally different from transactional operations
- **Maintainability**: SQL is the native language for data analysis

### Implementation Guidelines

#### When to Use ORM
- CRUD operations (Create, Read, Update, Delete)
- Business logic queries
- Cross-database compatibility needed
- Simple to moderate query complexity

#### When to Use Raw SQL
- Complex analytics with multiple aggregations
- Database-specific optimizations (PostgreSQL functions)
- Performance-critical reporting queries
- Window functions and CTEs for advanced analytics

### Code Organization
- **Raw SQL Queries**: Properly formatted, well-documented, with clear parameter binding
- **Type Safety**: Use Pydantic schemas for response validation
- **Security**: All queries use parameterized binding to prevent SQL injection
- **Testing**: Comprehensive test coverage for both happy path and edge cases

### Future Considerations
- **Monitoring**: Track query performance to identify optimization opportunities
- **Materialized Views**: Consider for large datasets if response times degrade
- **Query Optimization**: Use EXPLAIN ANALYZE to optimize complex analytics queries
- **Documentation**: Maintain clear documentation for complex business logic in SQL