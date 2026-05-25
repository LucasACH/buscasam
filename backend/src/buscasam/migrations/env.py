from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from buscasam.settings import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Honor an explicit URL passed via `cfg.set_main_option` (e.g. by the test
# harness, which spins up an isolated DB per session); otherwise fall back to
# the settings-derived default for the CLI workflow.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
