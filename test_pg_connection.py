from sqlalchemy import create_engine, inspect
engine = create_engine("postgresql+psycopg2://postgres:1234@localhost:5433/iot")
insp = inspect(engine)
print(insp.get_columns('sensors'))
