FROM alpine:3.20

RUN printf '%s\n' \
    'http://dl-cdn.alpinelinux.org/alpine/v3.20/main' \
    'http://dl-cdn.alpinelinux.org/alpine/v3.20/community' \
    > /etc/apk/repositories \
    && apk add --no-cache asterisk asterisk-opus asterisk-srtp ca-certificates

EXPOSE 5060/udp 5060/tcp 8088/tcp 12000-12100/udp

CMD ["asterisk", "-f", "-vvv"]
