FROM python:3.12-slim

# git is required by dbt for package management (dbt deps / dbt debug checks).
RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "dbt-bigquery>=1.8,<2.0"

WORKDIR /usr/app/dbt
# Profiles live in the mounted project dir; point dbt at it.
ENV DBT_PROFILES_DIR=/usr/app/dbt

ENTRYPOINT ["dbt"]
CMD ["--version"]
