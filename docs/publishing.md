# Publishing to PyPI and the official MCP Registry

This is a maintainer-only checklist. Normal users install from GitHub and do not need any of these
steps. Do not add `server.json` until the referenced package version is publicly available: the
official MCP Registry verifies the package and rejects metadata that points at a missing artifact.

## 1. One-time PyPI setup

The package name is `apple-music-playlists`. Before merging the publishing workflow, sign in to
PyPI and create a **pending trusted publisher** with exactly these values:

| Field | Value |
|---|---|
| PyPI project name | `apple-music-playlists` |
| GitHub owner | `Z-Han-Z` |
| GitHub repository | `apple-music-playlists` |
| Workflow filename | `publish-pypi.yml` |
| Environment name | `pypi` |

A pending publisher does not reserve the project name until the first successful upload. Create a
GitHub environment named `pypi` and require maintainer approval for deployment before running the
workflow. Trusted Publishing uses short-lived OIDC credentials; do not create or store a PyPI API
token in repository secrets.

Official references:

- [Creating a PyPI project with a Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
- [Publishing with a Trusted Publisher](https://docs.pypi.org/trusted-publishers/using-a-publisher/)

## 2. Publish the Python package

1. Confirm the target version in `am_paths.VERSION`, the Git tag, GitHub Release, and changelog.
2. Run the **publish PyPI package** workflow manually and enter the version without a leading `v`
   (for example, `1.3.0`). The workflow checks out the immutable `v<version>` tag before testing
   and building, so the PyPI artifact is made from the same source as the GitHub Release.
3. Approve the `pypi` environment deployment only after the build and offline test job succeeds.
4. Verify both the wheel and source distribution at
   `https://pypi.org/project/apple-music-playlists/`.
5. Install the public wheel in a clean environment and verify `am-mcp` initializes before
   publishing registry metadata.

The workflow is deliberately manual-only. Publishing a GitHub Release does not upload a package,
and pull requests never receive OIDC publish permission.

## 3. Publish official MCP Registry metadata

Only after the matching PyPI version exists:

1. Add the exact ownership marker below to the English README (it is already present when this
   checklist lands):

   ```html
   <!-- mcp-name: io.github.Z-Han-Z/apple-music-playlists -->
   ```

2. Generate `server.json` with the current `mcp-publisher init`, then review every field. Use:
   - name: `io.github.Z-Han-Z/apple-music-playlists`
   - package registry type: `pypi`
   - package identifier: `apple-music-playlists`
   - transport: `stdio`
   - package version: the exact published version, never `latest`
3. Run `mcp-publisher validate server.json`.
4. Authenticate with GitHub and publish. Interactive use is `mcp-publisher login github`; CI may
   use `mcp-publisher login github-oidc` with narrowly scoped `id-token: write` permission.
5. Read the published record back from the Registry API and verify its package, version,
   repository, title, and description.

Official references:

- [MCP Registry publisher quickstart](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/quickstart.mdx)
- [Supported package types and PyPI ownership verification](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/package-types.mdx)
- [Registry authentication and GitHub namespaces](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/authentication.mdx)
