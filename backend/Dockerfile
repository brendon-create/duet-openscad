FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    openscad \
    fontconfig \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /usr/share/fonts/truetype/google-fonts && \
    cd /tmp && \
    git clone --filter=blob:none --no-checkout https://github.com/google/fonts.git && \
    cd fonts && \
    git sparse-checkout init --cone && \
    git sparse-checkout set \
        ofl/abel \
        ofl/abrilfatface \
        ofl/adventpro \
        ofl/alegreya \
        ofl/alexbrush \
        ofl/alfaslabone \
        ofl/alice \
        ofl/allura \
        ofl/amaticsc \
        ofl/amiri \
        ofl/anton \
        ofl/arapey \
        ofl/archivo \
        ofl/armata \
        ofl/artifika \
        ofl/arvo \
        ofl/audiowide \
        ofl/average \
        ofl/baloo2 \
        ofl/bangers \
        ofl/bebasneue \
        ofl/belgrano \
        ofl/bentham \
        ofl/bitter \
        ofl/breeserif \
        ofl/bubblegumsans \
        ofl/bungee \
        ofl/cabin \
        ofl/cantataone \
        ofl/caudex \
        ofl/caveat \
        ofl/chivo \
        ofl/cinzel \
        ofl/comfortaa \
        ofl/commissioner \
        ofl/cookie \
        ofl/copse \
        ofl/cormorantgaramond \
        ofl/courierprime \
        ofl/coustard \
        ofl/creepster \
        ofl/cutivemono \
        ofl/dmseriftext \
        ofl/dancingscript \
        ofl/dosis \
        ofl/ebgaramond \
        ofl/eczar \
        ofl/encodesans \
        ofl/faunaone \
        ofl/firacode \
        ofl/firasans \
        ofl/fjallaone \
        ofl/fugazone \
        ofl/gelasio \
        ofl/gloriahallelujah \
        ofl/greatvibes \
        ofl/handlee \
        ofl/hind \
        ofl/holtwoodonesc \
        ofl/inconsolata \
        ofl/indieflower \
        ofl/jost \
        ofl/kalam \
        ofl/kanit \
        ofl/karla \
        ofl/lexend \
        ofl/lobster \
        ofl/merriweather \
        ofl/neuton \
        ofl/nunito \
        ofl/oldstandardtt \
        ofl/orbitron \
        ofl/oswald \
        ofl/outfit \
        ofl/pacifico \
        ofl/passionone \
        ofl/pathwaygothicone \
        ofl/patrickhand \
        ofl/paytoneone \
        ofl/playfairdisplay \
        ofl/poppins \
        ofl/prata \
        ofl/quicksand \
        ofl/righteous \
        ofl/rubik \
        ofl/russoone \
        ofl/sacramento \
        ofl/secularone \
        ofl/shadowsintolight \
        ofl/sharetechmono \
        ofl/shrikhand \
        ofl/sniglet \
        ofl/spacegrotesk \
        ofl/spacemono \
        ofl/spectral \
        ofl/tangerine \
        ofl/titanone \
        ofl/varelaround \
        ofl/vollkorn \
        ofl/zillaslab && \
    git checkout && \
    find ofl -name "*.ttf" -exec cp {} /usr/share/fonts/truetype/google-fonts/ \; && \
    cd /tmp && \
    rm -rf fonts && \
    fc-cache -f -v

RUN echo "=== Installed fonts count ===" && \
    fc-list : family | sort -u | wc -l && \
    echo "==========================="

COPY requirements.txt .
COPY app.py .
COPY scad_generator.py .

RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "300", "app:app"]
