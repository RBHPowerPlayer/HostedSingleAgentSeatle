"""
Seattle Hotel Agent - A simple agent with a tool to find hotels in Seattle.
Uses Microsoft Agent Framework with Azure AI Foundry.
Ready for deployment to Foundry Hosted Agent service.
"""

import asyncio
import os
from datetime import datetime
from typing import Annotated

from dotenv import load_dotenv

load_dotenv(override=True)

# RBH: [SSL/TLS] Build SSL context with corporate CA bundle BEFORE importing Azure/aiohttp modules.
# Python 3.13+ enables VERIFY_X509_STRICT by default, which rejects certificates
# missing the Authority Key Identifier extension (common in corporate proxy CAs).
import ssl
import aiohttp


def _build_ssl_context() -> ssl.SSLContext | None:
    """Build SSL context with corporate CA bundle added to system CAs."""
    ca_cert_path = os.getenv("CA_CERT_PATH", "ca-bundle.crt")
    if not ca_cert_path or not os.path.exists(ca_cert_path):
        return None
    
    # Start with system default context (includes system CA certificates)
    ctx = ssl.create_default_context()
    # Add corporate CA bundle ON TOP (doesn't replace system CAs)
    ctx.load_verify_locations(cafile=ca_cert_path)
    
    # Relax strict RFC-5280 enforcement for corporate proxy CAs that omit
    # the Authority Key Identifier extension (Python 3.13+ rejects them otherwise).
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    print(f"SSL: loaded CA bundle from {ca_cert_path} (appended to system CAs), VERIFY_X509_STRICT disabled")
    return ctx


_SSL_CONTEXT = _build_ssl_context()

# Patch aiohttp.TCPConnector so every connector created by the Azure SDK
# uses our custom ssl_context instead of the default system one.
if _SSL_CONTEXT is not None:
    _orig_connector_init = aiohttp.TCPConnector.__init__

    def _patched_connector_init(self, *args, **kwargs):
        # Only inject when the caller hasn't already set an explicit ssl value.
        if kwargs.get("ssl") is None or kwargs.get("ssl") is True:
            kwargs["ssl"] = _SSL_CONTEXT
        return _orig_connector_init(self, *args, **kwargs)

    aiohttp.TCPConnector.__init__ = _patched_connector_init

# RBH: [AGENT FRAMEWORK] Client qui connecte ton agent au modèle IA et gère la logique de conversation
from agent_framework.azure import AzureAIAgentClient
# RBH: [AGENT FRAMEWORK] MCPStdioTool permet d'ajouter un serveur MCP local (processus stdio) comme outil de l'agent
from agent_framework import MCPStdioTool

# RBH: [AGENT FRAMEWORK + MCP] Pattern MCP Sentinel (serveur distant HTTP/SSE) — voir sentinel_mcp.py
# RBH: À activer quand un serveur MCP Sentinel hébergé sera disponible (URL configurée dans .env)
from sentinel_mcp import create_sentinel_mcp_tool

# RBH: [Foundry Agent Service SDK (Azure AI AgentServer SDK)] Transforme l'agent en serveur HTTP compatible avec le protocole Foundry
from azure.ai.agentserver.agentframework import from_agent_framework
# RBH: [Foundry Agent Service SDK (Azure AI AgentServer SDK)] Gère l'authentification Azure — fonctionne aussi bien en local (az login) que sur Foundry (Managed Identity)
from azure.identity.aio import DefaultAzureCredential

# Configure these for your Foundry project
# Read the explicit variables present in the .env file
# RBH: [Foundry Agent Service SDK (Azure AI AgentServer SDK)] Ces deux variables sont la seule configuration nécessaire pour connecter l'agent à Foundry
PROJECT_ENDPOINT = os.getenv(
    "PROJECT_ENDPOINT"
)  # e.g., "https://<project>.services.ai.azure.com"
MODEL_DEPLOYMENT_NAME = os.getenv(
    "MODEL_DEPLOYMENT_NAME", "gpt-4o-mini"
)  # Your model deployment name e.g., "gpt-4.1-mini"

# RBH: [AGENT FRAMEWORK + MCP] Credentials de l'App Registration Azure pour authentifier le serveur MCP
# RBH: Prérequis : créer une App Registration dans Azure Portal → noter client_id, client_secret, tenant_id
# RBH: Aucune license Copilot M365 requise — fonctionne avec toute subscription Azure
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")      # App Registration → client ID
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")  # App Registration → secret
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID")      # Azure AD → tenant ID


# Simulated hotel data for Seattle
# RBH: [TON CODE] Source de données — indépendante du framework, remplace par ton API ou ta base de données
SEATTLE_HOTELS = [
    {
        "name": "Contoso Suites",
        "price_per_night": 189,
        "rating": 4.5,
        "location": "Downtown",
    },
    {
        "name": "Fabrikam Residences",
        "price_per_night": 159,
        "rating": 4.2,
        "location": "Pike Place Market",
    },
    {
        "name": "Alpine Ski House",
        "price_per_night": 249,
        "rating": 4.7,
        "location": "Seattle Center",
    },
    {
        "name": "Margie's Travel Lodge",
        "price_per_night": 219,
        "rating": 4.4,
        "location": "Waterfront",
    },
    {
        "name": "Northwind Inn",
        "price_per_night": 139,
        "rating": 4.0,
        "location": "Capitol Hill",
    },
    {
        "name": "Relecloud Hotel",
        "price_per_night": 99,
        "rating": 3.8,
        "location": "University District",
    },
]


# RBH: [TON CODE → AGENT FRAMEWORK] Cette fonction Python devient un "Tool" utilisable par l'agent.
# Concrètement : quand l'utilisateur demande des hôtels:
# - le modèle décide seul d'appeler cette fonction,
# - puis il choisit les bons arguments à partir du contexte de la conversation, puis intègre le résultat dans sa réponse.
# Le framework lit les Annotated["..."] et la docstring (c'est le texte entre triple guillemets """...""" ) pour générer automatiquement la description 
# de l'outil envoyée au modèle — sans eux, le modèle ne saurait pas quand ni comment appeler la fonction.
def get_available_hotels(
    check_in_date: Annotated[str, "Check-in date in YYYY-MM-DD format"],
    check_out_date: Annotated[str, "Check-out date in YYYY-MM-DD format"],
    max_price: Annotated[int, "Maximum price per night in USD (optional)"] = 500,
) -> str:
    """
    Get available hotels in Seattle for the specified dates.
    This simulates a call to a fake hotel availability API.
    """
    try:
        # Parse dates
        check_in = datetime.strptime(check_in_date, "%Y-%m-%d")
        check_out = datetime.strptime(check_out_date, "%Y-%m-%d")

        # Validate dates
        if check_out <= check_in:
            return "Error: Check-out date must be after check-in date."

        nights = (check_out - check_in).days

        # Filter hotels by price
        available_hotels = [
            hotel for hotel in SEATTLE_HOTELS if hotel["price_per_night"] <= max_price
        ]

        if not available_hotels:
            return (
                f"No hotels found in Seattle within your budget of ${max_price}/night."
            )

        # Build response
        result = f"Available hotels in Seattle from {check_in_date} to {check_out_date} ({nights} nights):\n\n"

        for hotel in available_hotels:
            total_cost = hotel["price_per_night"] * nights
            result += f"**{hotel['name']}**\n"
            result += f"   Location: {hotel['location']}\n"
            result += f"   Rating: {hotel['rating']}/5\n"
            result += f"   ${hotel['price_per_night']}/night (Total: ${total_cost})\n\n"

        return result

    except ValueError as e:
        return f"Error parsing dates. Please use YYYY-MM-DD format. Details: {str(e)}"


async def main():
    """Main function to run the agent as a web server."""
    async with (
        # RBH: [Foundry Agent Service SDK (Azure AI AgentServer SDK)] Gère l'auth Azure automatiquement selon l'environnement d'exécution
        DefaultAzureCredential() as credential,
        # RBH: [AGENT FRAMEWORK] Ouvre la connexion au modèle IA — doit rester ouvert pendant toute la durée du serveur
        AzureAIAgentClient(
            project_endpoint=PROJECT_ENDPOINT,
            model_deployment_name=MODEL_DEPLOYMENT_NAME,
            credential=credential,
        ) as client,
    ):
        # RBH: [AGENT FRAMEWORK + MCP] Azure MCP Server — serveur MCP officiel Microsoft (github.com/Azure/azure-mcp)
        # RBH: Lancé comme processus local via npx, authentifié par les variables AZURE_* de l'App Registration
        # RBH: Expose des outils Azure (Storage, Key Vault, Resource Manager, etc.) et authentification équivalente à Sentinel
        # azure_mcp_tool = MCPStdioTool(
        #     name="azure-mcp",
        #     command="npx",
        #     args=["-y", "@azure/mcp@latest", "server", "start"],
        #     env={
        #         "AZURE_CLIENT_ID": AZURE_CLIENT_ID,
        #         "AZURE_CLIENT_SECRET": AZURE_CLIENT_SECRET,
        #         "AZURE_TENANT_ID": AZURE_TENANT_ID,
        #     },
        # )

        # RBH: [AGENT FRAMEWORK + MCP] Sentinel MCP Server distant — à activer quand SENTINEL_MCP_URL est configurée
        # RBH: Voir sentinel_mcp.py pour le détail du pattern HTTP/SSE + auth App Registration
        sentinel_mcp_tool = await create_sentinel_mcp_tool()

        # RBH: [AGENT FRAMEWORK] Définit le comportement de l'agent (instructions) et lui enregistre les outils Python disponibles
        agent = client.create_agent(
            name="SeattleHotelAgent",
            instructions="""You are a helpful travel assistant specializing in finding hotels in Seattle, Washington.

When a user asks about hotels in Seattle:
1. Ask for their check-in and check-out dates if not provided
2. Ask about their budget preferences if not mentioned
3. Use the get_available_hotels tool to find available options
4. Present the results in a friendly, informative way
5. Offer to help with additional questions about the hotels or Seattle

Be conversational and helpful. If users ask about things outside of Seattle hotels,
politely let them know you specialize in Seattle hotel recommendations.""",
            # tools=[get_available_hotels, sentinel_mcp_tool], #, sentinel_mcp_tool] une fois que le MCP Sentinel distant est prêt, ajoute-le à la liste des outils disponibles de l'agent 
            tools=[get_available_hotels]#, sentinel_mcp_tool] #une fois que le MCP Sentinel distant est prêt, ajoute-le à la liste des outils disponibles de l'agent 
        )

        # RBH: [Foundry Agent Service SDK (Azure AI AgentServer SDK)] Encapsule l'agent dans un serveur HTTP — c'est ce serveur que Foundry appelle lors du déploiement
        print("Seattle Hotel Agent Server running on http://localhost:8088")
        server = from_agent_framework(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
