FROM debian:13

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-apt \
        sudo \
        ca-certificates \
        curl \
        gnupg \
        iptables \
        uidmap \
        procps \
    && rm -rf /var/lib/apt/lists/*

CMD ["sleep", "infinity"]
