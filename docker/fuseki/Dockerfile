ARG JAVA_VERSION=21-jre-jammy
FROM eclipse-temurin:${JAVA_VERSION}

ARG FUSEKI_VERSION=6.2.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 fuseki \
    && mkdir -p /opt/fuseki /fuseki/data \
    && chown -R fuseki:fuseki /opt/fuseki /fuseki

WORKDIR /opt/fuseki

# Distribution officielle Apache Jena depuis Maven Central.
RUN set -eu; \
    artifact="jena-fuseki-server-${FUSEKI_VERSION}.jar"; \
    download_url="https://repo.maven.apache.org/maven2/org/apache/jena/jena-fuseki-server/${FUSEKI_VERSION}/${artifact}"; \
    curl --fail --location --retry 3 "$download_url" --output fuseki.jar; \
    curl --fail --location --retry 3 "${download_url}.sha1" --output fuseki.jar.sha1; \
    checksum="$(cat fuseki.jar.sha1)"; \
    printf '%s  fuseki.jar\n' "$checksum" | sha1sum --check -; \
    rm fuseki.jar.sha1

COPY entrypoint.sh /opt/fuseki/entrypoint.sh

USER fuseki
EXPOSE 3030
ENTRYPOINT ["sh", "/opt/fuseki/entrypoint.sh"]

