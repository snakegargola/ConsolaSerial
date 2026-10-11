# Publicar el proyecto en GitHub

1. Crear un commit y subirlo a la rama `main`.
2. Crear un tag de versión:

```bash
git tag -a v1.0.0 -m "v1.0.0"
git push origin v1.0.0
```

El workflow `.github/workflows/release-binaries.yml` compila únicamente el
binario Linux y publica `SerialMonitor-linux`, su paquete `.tar.gz` y los
checksums.
