FROM bitnami/spark:3.5
USER root
# Bitnami images have helper "install_packages" on Debian/Ubuntu bases
RUN install_packages python3 python3-venv python3-pip || \
    (apt-get update && apt-get install -y python3 python3-venv python3-pip && rm -rf /var/lib/apt/lists/*)
RUN ln -sf /usr/bin/python3 /usr/local/bin/python3
USER 1001
