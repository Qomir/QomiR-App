"""Shopify Admin GraphQL API (application personnalisée, jeton Admin API).

Portées nécessaires : read_orders, read_products, write_products, read_inventory,
write_files, read_files, read_shopify_payments_disputes, read_customers.
"""
from __future__ import annotations

import mimetypes
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .http import ApiError, request

API_VERSION = "2025-10"

ORDERS_QUERY = """
query Orders($q: String!, $cursor: String) {
  orders(first: 100, query: $q, after: $cursor, sortKey: CREATED_AT) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id name createdAt cancelledAt email
      displayFinancialStatus displayFulfillmentStatus
      totalPriceSet { shopMoney { amount } }
      totalShippingPriceSet { shopMoney { amount } }
      totalRefundedSet { shopMoney { amount } }
      lineItems(first: 20) { nodes { quantity title variant { inventoryItem { unitCost { amount } } } } }
      fulfillments(first: 5) {
        createdAt status displayStatus deliveredAt inTransitAt
        trackingInfo(first: 3) { number url company }
      }
      customerJourneySummary {
        lastVisit { utmParameters { source medium campaign content } }
        firstVisit { utmParameters { source medium campaign content } }
      }
    }
  }
}"""

PRODUCTS_QUERY = """
query Products($q: String) {
  products(first: 50, query: $q) {
    nodes {
      id title handle status descriptionHtml tags productType totalInventory updatedAt
      seo { title description }
      media(first: 6) { nodes { ... on MediaImage { image { url } } } }
      variants(first: 20) { nodes { id title price inventoryQuantity } }
    }
  }
}"""

DISPUTES_QUERY = """
query { shopifyPaymentsAccount { disputes(first: 20) { nodes {
  id status initiatedAt amount { amount } reasonDetails { reason } order { name } } } } }"""


class ShopifyClient:
    def __init__(self, shop: str, token: str):
        self.url = f"https://{shop}/admin/api/{API_VERSION}/graphql.json"
        self.headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    def gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = request("shopify", "POST", self.url, headers=self.headers, json={"query": query, "variables": variables or {}})
        body = resp.json()
        if body.get("errors"):
            raise ApiError("shopify", resp.status_code, str(body["errors"])[:500])
        return body["data"]

    # -- commandes -----------------------------------------------------------
    def orders_since(self, since: datetime) -> list[dict[str, Any]]:
        q = f"created_at:>='{since.isoformat()}'"
        out, cursor = [], None
        while True:
            data = self.gql(ORDERS_QUERY, {"q": q, "cursor": cursor})["orders"]
            out += [normalize_order(n) for n in data["nodes"]]
            if not data["pageInfo"]["hasNextPage"]:
                return out
            cursor = data["pageInfo"]["endCursor"]

    def open_orders(self) -> list[dict[str, Any]]:
        data = self.gql(ORDERS_QUERY, {"q": "status:open financial_status:paid", "cursor": None})["orders"]
        return [normalize_order(n) for n in data["nodes"]]

    def find_orders(self, email: str = "", name: str = "") -> list[dict[str, Any]]:
        q = f"name:{name}" if name else f"email:{email}"
        return [normalize_order(n) for n in self.gql(ORDERS_QUERY, {"q": q, "cursor": None})["orders"]["nodes"]]

    def disputes(self) -> list[dict[str, Any]]:
        try:
            acc = self.gql(DISPUTES_QUERY)["shopifyPaymentsAccount"]
        except ApiError:
            return []
        if not acc:
            return []
        return [{"id": d["id"], "status": d["status"], "amount": float(d["amount"]["amount"]),
                 "reason": (d.get("reasonDetails") or {}).get("reason"), "order": (d.get("order") or {}).get("name"),
                 "initiated_at": d["initiatedAt"]} for d in acc["disputes"]["nodes"]]

    # -- produits --------------------------------------------------------------
    def products(self, query: str | None = None) -> list[dict[str, Any]]:
        nodes = self.gql(PRODUCTS_QUERY, {"q": query})["products"]["nodes"]
        return [normalize_product(n) for n in nodes]

    def create_draft_product(self, p: dict[str, Any]) -> str:
        mutation = """mutation($product: ProductCreateInput!) { productCreate(product: $product) {
            product { id } userErrors { field message } } }"""
        data = self.gql(mutation, {"product": {
            "title": p["title"], "descriptionHtml": p.get("description_html", ""), "status": "DRAFT",
            "tags": p.get("tags", []), "productType": p.get("category", ""), "vendor": "PrecisVis"}})
        errs = data["productCreate"]["userErrors"]
        if errs:
            raise ApiError("shopify", 422, str(errs))
        return data["productCreate"]["product"]["id"]

    def update_product(self, product_id: str, *, description_html: str, seo_title: str, seo_description: str) -> None:
        mutation = """mutation($product: ProductUpdateInput!) { productUpdate(product: $product) {
            product { id } userErrors { field message } } }"""
        data = self.gql(mutation, {"product": {"id": product_id, "descriptionHtml": description_html,
                                               "seo": {"title": seo_title, "description": seo_description}}})
        errs = data["productUpdate"]["userErrors"]
        if errs:
            raise ApiError("shopify", 422, str(errs))

    # -- fichiers (hébergement des créas pour Instagram / Facebook) ---------------
    def upload_file(self, path: Path) -> str:
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        is_video = mime.startswith("video/")
        staged = self.gql("""mutation($input: [StagedUploadInput!]!) { stagedUploadsCreate(input: $input) {
            stagedTargets { url resourceUrl parameters { name value } } userErrors { message } } }""",
                          {"input": [{"filename": path.name, "mimeType": mime, "httpMethod": "POST",
                                      "resource": "VIDEO" if is_video else "IMAGE",
                                      "fileSize": str(path.stat().st_size)}]})["stagedUploadsCreate"]
        target = staged["stagedTargets"][0]
        fields = {p["name"]: p["value"] for p in target["parameters"]}
        with open(path, "rb") as fh:
            request("shopify-upload", "POST", target["url"], data=fields, files={"file": (path.name, fh, mime)}, timeout=300)
        created = self.gql("""mutation($files: [FileCreateInput!]!) { fileCreate(files: $files) {
            files { id } userErrors { message } } }""",
                           {"files": [{"originalSource": target["resourceUrl"],
                                       "contentType": "VIDEO" if is_video else "IMAGE"}]})["fileCreate"]
        if created["userErrors"]:
            raise ApiError("shopify", 422, str(created["userErrors"]))
        file_id = created["files"][0]["id"]
        for _ in range(30):
            node = self.gql("""query($id: ID!) { node(id: $id) { ... on MediaImage { fileStatus image { url } }
                               ... on Video { fileStatus sources { url mimeType } } } }""", {"id": file_id})["node"]
            if node and node.get("fileStatus") == "READY":
                if node.get("image"):
                    return node["image"]["url"]
                mp4 = [s for s in node.get("sources", []) if s["mimeType"] == "video/mp4"]
                return (mp4 or node["sources"])[0]["url"]
            if node and node.get("fileStatus") == "FAILED":
                raise ApiError("shopify", None, f"échec du traitement du fichier {path.name}")
            time.sleep(5)
        raise ApiError("shopify", None, f"fichier {path.name} toujours en traitement")


def _money(node: dict | None) -> float:
    try:
        return float(node["shopMoney"]["amount"])  # type: ignore[index]
    except (TypeError, KeyError):
        return 0.0


def normalize_order(n: dict[str, Any]) -> dict[str, Any]:
    journey = n.get("customerJourneySummary") or {}
    utm = ((journey.get("lastVisit") or {}).get("utmParameters") or (journey.get("firstVisit") or {}).get("utmParameters") or {})
    lines = []
    for li in n["lineItems"]["nodes"]:
        cost = (((li.get("variant") or {}).get("inventoryItem") or {}).get("unitCost") or {}).get("amount")
        lines.append({"title": li["title"], "qty": li["quantity"], "unit_cost": float(cost) if cost else None})
    fulfillments = [{
        "created_at": f["createdAt"], "status": f["status"], "display_status": f.get("displayStatus"),
        "delivered_at": f.get("deliveredAt"), "in_transit_at": f.get("inTransitAt"),
        "tracking": [t["number"] for t in f.get("trackingInfo", []) if t.get("number")],
    } for f in n.get("fulfillments", [])]
    return {
        "id": n["id"], "name": n["name"], "created_at": n["createdAt"], "cancelled": bool(n.get("cancelledAt")),
        "email": n.get("email"), "financial_status": n["displayFinancialStatus"],
        "fulfillment_status": n["displayFulfillmentStatus"], "total": _money(n["totalPriceSet"]),
        "shipping_paid": _money(n.get("totalShippingPriceSet")), "refunded": _money(n.get("totalRefundedSet")),
        "lines": lines, "fulfillments": fulfillments,
        "utm_source": (utm.get("source") or "").lower() or None, "utm_content": utm.get("content"),
    }


def normalize_product(n: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": n["id"], "title": n["title"], "handle": n["handle"], "status": n["status"],
        "description_html": n.get("descriptionHtml") or "", "tags": n.get("tags", []),
        "category": n.get("productType", ""), "inventory": n.get("totalInventory"),
        "seo": n.get("seo") or {}, "updated_at": n.get("updatedAt"),
        "images": [m["image"]["url"] for m in n["media"]["nodes"] if m.get("image")],
        "variants": [{"id": v["id"], "title": v["title"], "price": float(v["price"]), "inventory": v.get("inventoryQuantity")}
                     for v in n["variants"]["nodes"]],
    }
