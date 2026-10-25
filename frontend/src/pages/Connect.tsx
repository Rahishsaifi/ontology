import { useState } from "react";
import { api } from "../api";
import { Button, CodeBlock, ErrorText, Field, PageIntro, Panel } from "../components";

export function ConnectPage() {
  const [baseUrl, setBaseUrl] = useState("");
  const [authMethod, setAuthMethod] = useState("oauth_bearer");
  const [accessToken, setAccessToken] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [tokenUrl, setTokenUrl] = useState("");
  const [clientId, setClientId] = useState("");
  const [samlAssertion, setSamlAssertion] = useState("");
  const [remember, setRemember] = useState(true);
  const [result, setResult] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function testConnection() {
    setError(null);
    try {
      const response = await api<Record<string, unknown>>("/api/connections/successfactors/test", {
        method: "POST",
        body: JSON.stringify({
          base_url: baseUrl || null,
          auth_method: authMethod,
          access_token: accessToken || null,
          username: username || null,
          password: password || null,
          company_id: companyId || null,
          token_url: tokenUrl || null,
          client_id: clientId || null,
          saml_assertion: samlAssertion || null,
          remember_for_session: remember,
        }),
      });
      setAccessToken("");
      setPassword("");
      setSamlAssertion("");
      setResult(JSON.stringify(response, null, 2));
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <div>
      <PageIntro
        kicker="Tenant"
        title="Connect"
        body="Test SuccessFactors access. Secrets stay in API memory for this session and are cleared from the form after a successful test."
      />
      <Panel
        title="SuccessFactors endpoint"
        action={
          <Button
            kind="quiet"
            onClick={() =>
              api("/api/connections/successfactors/session", { method: "DELETE" }).then(() =>
                setResult("Session credentials cleared."),
              )
            }
          >
            Clear session
          </Button>
        }
      >
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Base URL" value={baseUrl} onChange={setBaseUrl} placeholder="https://apiX.successfactors.com/odata/v2" />
          <label className="block text-sm">
            <span className="muted mb-1 block text-xs font-medium uppercase tracking-[0.08em]">Auth method</span>
            <select className="field" value={authMethod} onChange={(event) => setAuthMethod(event.target.value)}>
              <option value="oauth_bearer">oauth_bearer</option>
              <option value="basic">basic</option>
              <option value="oauth_saml_bearer">oauth_saml_bearer</option>
            </select>
          </label>
          <Field label="Access token" value={accessToken} onChange={setAccessToken} secret />
          <Field label="Username" value={username} onChange={setUsername} />
          <Field label="Password" value={password} onChange={setPassword} secret />
          <Field label="Company ID" value={companyId} onChange={setCompanyId} />
          <Field label="Token URL" value={tokenUrl} onChange={setTokenUrl} />
          <Field label="Client ID" value={clientId} onChange={setClientId} />
          <div className="md:col-span-2">
            <Field label="SAML assertion" value={samlAssertion} onChange={setSamlAssertion} secret />
          </div>
        </div>
        <label className="mt-4 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />
          Remember in API memory until the session is cleared
        </label>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button onClick={testConnection}>Test connection</Button>
          <ErrorText error={error} />
        </div>
        {result ? (
          <div className="mt-4">
            <CodeBlock>{result}</CodeBlock>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}
