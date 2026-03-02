# Publicar proyecto en GitHub (release automática)

## 1) Inicializar repo local (si aún no existe)

```bash
git init
git add .
git commit -m "feat: initial release of Serial Monitor"
```

## 2) Conectar con tu repositorio remoto

```bash
git branch -M main
git remote add origin https://github.com/<TU_USUARIO>/<TU_REPO>.git
git push -u origin main
```

## 3) Crear tag de versión (dispara build automática)

```bash
git tag -a v1.0.0 -m "v1.0.0"
git push origin v1.0.0
```

## 4) Esperar workflow de GitHub Actions

Workflow: `.github/workflows/release-binaries.yml`

Este workflow compila automáticamente:

- `SerialMonitor-windows.exe`
- `SerialMonitor-linux`

y los publica como assets del release junto con `SHA256SUMS.txt`.

## 5) Crear release en GitHub (si no existe)

En GitHub: **Releases > Draft a new release**

- Tag: `v1.0.0`
- Título: `Serial Monitor v1.0.0`
- Descripción: usa `.github/release-template.md`
- Si empujaste un tag `v*`, el workflow adjunta assets automáticamente

## 6) Verificación rápida

- README visible y claro
- LICENSE presente
- Build docs correctos
- Archivos pesados y venv excluidos por `.gitignore`
- Assets del release disponibles para descarga directa
