# Rust Tool Action

Build and package simple command-line tools built with Rust and Cargo

## Use this action

Create a file in your repository at `.github/workflows/release.yaml` based on the following:

```yaml
name: Release

env:
  tool_name: my-tool
  build_type: release

permissions:
  contents: write

on:
  push:
    tags:
      - v*.*.*

jobs:
  release:
    strategy:
      matrix:
        target:
          - aarch64-apple-darwin
          - x86_64-apple-darwin
          - x86_64-pc-windows-msvc
          - x86_64-unknown-linux-musl
        include:
          - target: aarch64-apple-darwin
            executable_ext:
            archive_type: .tar.gz
            build_os: macos-latest
          - target: x86_64-apple-darwin
            executable_ext:
            archive_type: .tar.gz
            build_os: macos-latest
          - target: x86_64-pc-windows-msvc
            executable_ext: .exe
            archive_type: .zip
            build_os: windows-latest
          - target: x86_64-unknown-linux-musl
            executable_ext:
            archive_type: .tar.gz
            build_os: ubuntu-latest
    runs-on: ${{ matrix.build_os }}
    name: Release Rust Tool
    steps:
      - name: Check out
        uses: actions/checkout@v3

      - name: Release Rust Tool
        id: release_rust_tool
        uses: rcook/rust-tool-action@v0.0.23
        with:
          tool_name: ${{ env.tool_name }}
          target: ${{ matrix.target }}
          executable_ext: ${{ matrix.executable_ext }}
          archive_type: ${{ matrix.archive_type }}
          build_type: ${{ env.build_type }}
          code_sign: true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          RUST_TOOL_ACTION_CODE_SIGN_CRT: ${{ secrets.CRT }}
          RUST_TOOL_ACTION_CODE_SIGN_CRTPASS: ${{ secrets.CRTPASS }}
```
