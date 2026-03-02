"""
Sentinel MCP Remote Tool - Pattern d'intégration pour Microsoft Sentinel MCP Server.

RBH: Ce fichier montre comment connecter l'agent à un serveur MCP distant (HTTP/SSE)
avec authentification via App Registration (ClientSecretCredential).

PRÉREQUIS :
  - Un serveur MCP Sentinel hébergé et accessible via URL HTTP
  - Une App Registration avec les permissions :
      "Microsoft Sentinel Reader" sur le workspace Log Analytics
      ou "Microsoft Sentinel Contributor" pour des actions en écriture
  - Variables d'environnement : AZURE_CLIENT_ID, AZURE_CLIENT_SECRET,
    AZURE_TENANT_ID, SENTINEL_MCP_URL

NOTE :Ce pattern est prêt à l'emploi dès qu'une URL sera disponible.
"""

import os

# RBH: [AGENT FRAMEWORK] MCPStreamableHTTPTool connecte l'agent à un serveur MCP distant via HTTP/SSE
# Contrairement à MCPStdioTool (processus local utilisé pour Azure MCP), ici le serveur tourne ailleurs (Azure, cloud, etc.)
from agent_framework import MCPStreamableHTTPTool

# RBH: [AZURE AUTH] ClientSecretCredential = auth via App Registration
# Utilise client_id + client_secret + tenant_id — aucune interaction humaine requise
from azure.identity.aio import ClientSecretCredential

# RBH: URL du serveur MCP Sentinel hébergé — définie dans .env (SENTINEL_MCP_URL)
SENTINEL_MCP_URL = os.getenv("SENTINEL_MCP_URL")

# RBH: Credentials App Registration — mêmes que pour Azure MCP
SENTINEL_CLIENT_ID = os.getenv("SENTINEL_CLIENT_ID")
SENTINEL_CLIENT_SECRET = os.getenv("SENTINEL_CLIENT_SECRET")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")


async def get_sentinel_token() -> str:
    """
    RBH: [AZURE AUTH] Obtient un token OAuth2 pour authentifier les appels au serveur MCP Sentinel.

    Scope utilisé : "https://management.azure.com/.default"
    → Donne accès aux APIs Azure Resource Manager, dont Microsoft Sentinel.

    Le token est de type Bearer et doit être passé dans le header HTTP Authorization.
    """
    # RBH: ClientSecretCredential crée le token depuis les credentials de l'App Registration
    async with ClientSecretCredential(
        tenant_id=AZURE_TENANT_ID,
        client_id=SENTINEL_CLIENT_ID,
        client_secret=SENTINEL_CLIENT_SECRET,
    ) as credential:
        # RBH: "/.default" = toutes les permissions déléguées configurées sur l'App Registration
        token = await credential.get_token("https://management.azure.com/.default")
        return token.token


async def create_sentinel_mcp_tool() -> MCPStreamableHTTPTool | None:
    """
    RBH: [AGENT FRAMEWORK + MCP] Crée et retourne l'outil MCP Sentinel prêt à être ajouté à l'agent.

    Retourne None si SENTINEL_MCP_URL n'est pas configurée (placeholder ou absente).

    Flux :
      1. Obtient un token Bearer via App Registration
      2. Configure MCPStreamableHTTPTool avec ce token dans le header Authorization
      3. load_tools=True → le framework découvre automatiquement les outils exposés par le serveur

    À appeler dans main() avant de créer l'agent.
    """
    # RBH: Si l'URL n'est pas configurée ou est encore un placeholder, on skippe silencieusement
    if not SENTINEL_MCP_URL or "<" in SENTINEL_MCP_URL:
        print("Sentinel MCP: SENTINEL_MCP_URL non configurée — outil désactivé.")
        return None

    # RBH: Récupère le token OAuth2 pour authentifier les appels HTTP vers le serveur MCP
    token = await get_sentinel_token()

    # RBH: [AGENT FRAMEWORK] MCPStreamableHTTPTool — connexion HTTP/SSE à un serveur MCP distant
    # headers → transporte le token Bearer pour l'authentification
    # load_tools=True → le framework interroge le serveur pour lister ses outils disponibles
    sentinel_mcp_tool = MCPStreamableHTTPTool(
        name="sentinel-mcp",
        url=SENTINEL_MCP_URL,
        headers={
            "Authorization": f"Bearer {token}"
        },
        load_tools=True,
    )
    
    return sentinel_mcp_tool
