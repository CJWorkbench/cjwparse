# We run everything in a Dockerfile so we can pull arrow-tools binaries
FROM workbenchdata/arrow-tools:v0.0.12 as arrow-tools

FROM python:3.8.3-buster AS test

COPY --from=arrow-tools /usr/bin/csv-to-arrow /usr/bin/csv-to-arrow
COPY --from=arrow-tools /usr/bin/json-to-arrow /usr/bin/json-to-arrow
COPY --from=arrow-tools /usr/bin/xls-to-arrow /usr/bin/xls-to-arrow
COPY --from=arrow-tools /usr/bin/xlsx-to-arrow /usr/bin/xlsx-to-arrow

RUN pip install black pyflakes isort

# README is read by setup.py
COPY setup.py README.md /app/
# __version__ (for setup.py)
COPY cjwparse/__init__.py /app/cjwparse/
WORKDIR /app
RUN pip install .[tests,maintenance]

COPY . /app/

RUN true \
      && ./setup.py extract_messages --check \
      && pyflakes . \
      && black --check . \
      && isort --check-only --diff --recursive cjwparse tests \
      && pytest --verbose
