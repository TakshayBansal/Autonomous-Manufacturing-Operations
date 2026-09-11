/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const backend = process.env.API_INTERNAL_BASE_URL || "http://127.0.0.1:8000";
    return [{ source: "/backend/:path*", destination: `${backend}/:path*` }];
  },
  async redirects() {
    return [
      ["/v2/home", "/operations"], ["/v2/my-work", "/operations/my-work"],
      ["/v2/operations", "/operations/production"], ["/v2/materials", "/operations/materials"],
      ["/v2/quality", "/operations/quality"], ["/v2/maintenance", "/operations/maintenance"],
      ["/v2/improvement", "/operations/improvement"], ["/v2/knowledge", "/operations/knowledge"],
      ["/v2/briefing", "/operations/briefing"], ["/v2/admin", "/operations/admin"],
      ["/v2/integrations", "/operations/integrations"], ["/v2/setup", "/operations/setup"],
      ["/v2/corporate", "/operations/corporate"], ["/v2/profile", "/operations/profile"],
      ["/v2/deviations/:deviationId", "/operations/deviations/:deviationId"],
      ["/v2/maintenance/assets/:assetId", "/operations/maintenance/assets/:assetId"],
      ["/v2/materials/procurement", "/operations/materials/procurement"],
      ["/v2/materials/readiness", "/operations/materials/readiness"],
      ["/v2/operations/lines/:lineId", "/operations/production/lines/:lineId"],
      ["/v2/quality/deviations/:id", "/operations/quality/deviations/:id"],
      ["/control-centre", "/procurement"], ["/rfq-builder", "/procurement/rfqs"],
      ["/quotes", "/procurement/quotations"], ["/evidence", "/procurement/evidence"],
      ["/comparison", "/procurement/comparison"], ["/approvals", "/procurement/approvals"],
      ["/negotiations", "/procurement/negotiations"], ["/po-drafts", "/procurement/orders"],
      ["/inbound", "/procurement/inbound"], ["/gate", "/procurement/gate"],
      ["/store", "/procurement/store"], ["/quality", "/procurement/quality"],
      ["/invoices", "/procurement/invoices"],
      ["/outbox", "/procurement/outbox"], ["/audit", "/procurement/audit"],
      ["/integrations", "/procurement/integrations"],
      ["/workspace/setup", "/procurement/setup"], ["/agent", "/procurement"],
    ].map(([source, destination]) => ({ source, destination, permanent: false }));
  }
};

export default nextConfig;
