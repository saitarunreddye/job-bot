#!/usr/bin/env python3
import os
import tempfile
from tests.test_utils import create_test_database
from sqlalchemy import create_engine, text

# Create a temporary database
temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
temp_db.close()
url = f'sqlite:///{temp_db.name}'

print(f'Creating database at {temp_db.name}')
create_test_database(url)

# Check the database
engine = create_engine(url)
with engine.connect() as conn:
    result = conn.execute(text('PRAGMA table_info(jobs)'))
    print('Jobs table columns:')
    for row in result.fetchall():
        print(f'  {row[1]} ({row[2]})')

conn.close()
os.unlink(temp_db.name)
print('Database deleted')

