import { useEffect, useState } from "react";
import { api } from "../api";
import { Button, CodeBlock, ErrorText, Field, PageIntro, Panel } from "../components";

type ConnectDefaults = {
  base_url: string;
  auth_method: string;
  read_only: boolean;
};

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
  const [userId, setUserId] = useState("");
  const [privateKey, setPrivateKey] = useState("");
  const [userKey, setUserKey] = useState("");
  const [idpUrl, setIdpUrl] = useState("");
  const [remember, setRemember] = useState(true);
  const [fromEnv, setFromEnv] = useState(false);
  const [result, setResult] = useState("");
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    api<{ successfactors: ConnectDefaults }>("/api/health")
      .then((health) => {
        const sf = health.successfactors;
        if (sf.base_url) {
          setBaseUrl(sf.base_url);
          setFromEnv(true);
        }
        if (sf.auth_method) {
          setAuthMethod(sf.auth_method);
        }
      })
      .catch(() => undefined);
  }, []);

  function normalizeToken(value: string): string {
    const trimmed = value.trim();
    return trimmed.replace(/^Bearer\s+/i, "").trim();
  }

  async function testConnection() {
    setError(null);
    setResult("");
    const token = normalizeToken(accessToken);
    if (authMethod === "oauth_bearer" && !token) {
      setError(new Error("Paste the SuccessFactors access_token from Postman into Access token."));
      return;
    }
    if (!baseUrl.trim()) {
      setError(new Error("Base URL is required, for example https://apiX.successfactors.com/odata/v2"));
      return;
    }
    try {
      const response = await api<Record<string, unknown>>("/api/connections/successfactors/test", {
        method: "POST",
        body: JSON.stringify({
          base_url: baseUrl.trim() || null,
          auth_method: authMethod,
          access_token: token || null,
          username: username || null,
          password: password || null,
          company_id: companyId || null,
          token_url: tokenUrl || null,
          client_id: clientId || null,
          saml_assertion: samlAssertion || null,
          user_id: userId || null,
          private_key: privateKey || null,
          user_key: userKey || null,
          idp_url: idpUrl || null,
          remember_for_session: remember,
        }),
      });
      setAccessToken("");
      setPassword("");
      setSamlAssertion("");
      setPrivateKey("");
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
        body="Read-only: this app only GETs OData metadata and entity feeds. It never creates, updates, or deletes SuccessFactors records. Paste the access token manually; Base URL can come from SF_BASE_URL in .env."
      />
      <Panel
        title="SuccessFactors endpoint"
        lead={
          fromEnv
            ? "Base URL was loaded from SF_BASE_URL in .env. Paste only the access token below."
            : "Set SF_BASE_URL in .env to prefill Base URL, or enter it here."
        }
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
          <Field
            label="Base URL"
            value={baseUrl}
            onChange={(value) => {
              setBaseUrl(value);
              setFromEnv(false);
            }}
            placeholder="https://apiX.successfactors.com/odata/v2"
            hint={fromEnv ? "Prefilled from .env (SF_BASE_URL)." : undefined}
          />
          <label className="block text-sm">
            <span className="mb-1 block text-xs font-medium uppercase tracking-[0.08em] text-[var(--muted)]">
              Auth method
            </span>
            <select className="field" value={authMethod} onChange={(event) => setAuthMethod(event.target.value)}>
              <option value="oauth_bearer">oauth_bearer (Postman access token)</option>
              <option value="oauth_saml_private_key">oauth_saml_private_key</option>
              <option value="oauth_saml_bearer">oauth_saml_bearer (paste assertion)</option>
              <option value="basic">basic</option>
            </select>
          </label>

          {authMethod === "oauth_saml_private_key" ? (
            <>
              <Field label="Company ID" value={companyId} onChange={setCompanyId} />
              <Field label="Client ID" value={clientId} onChange={setClientId} />
              <Field label="User ID" value={userId} onChange={setUserId} hint="Sent as user_id to the IdP." />
              <Field
                label="User key header"
                value={userKey}
                onChange={setUserKey}
                hint="HTTP header user_key. Leave blank to reuse User ID."
              />
              <Field
                label="Token URL"
                value={tokenUrl}
                onChange={setTokenUrl}
                placeholder="https://apiX.successfactors.com/oauth/token"
              />
              <Field
                label="IdP URL"
                value={idpUrl}
                onChange={setIdpUrl}
                placeholder="optional · defaults to …/oauth/idp"
                hint="Only needed if your IdP is not the usual /oauth/idp next to token_url."
              />
              <div className="md:col-span-2">
                <Field
                  label="Private key (PEM)"
                  value={privateKey}
                  onChange={setPrivateKey}
                  multiline
                  placeholder={"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"}
                />
              </div>
            </>
          ) : null}

          {authMethod === "oauth_bearer" ? (
            <div className="md:col-span-2">
              <Field
                label="Access token"
                value={accessToken}
                onChange={setAccessToken}
                multiline
                placeholder="Paste the Bearer access_token from Postman"
                hint="Only the token value, without the word Bearer. Cleared from this form after a successful test."
              />
            </div>
          ) : null}

          {authMethod === "basic" ? (
            <>
              <Field label="Username" value={username} onChange={setUsername} />
              <Field label="Password" value={password} onChange={setPassword} secret />
              <Field label="Company ID" value={companyId} onChange={setCompanyId} />
            </>
          ) : null}

          {authMethod === "oauth_saml_bearer" ? (
            <>
              <Field label="Company ID" value={companyId} onChange={setCompanyId} />
              <Field label="Client ID" value={clientId} onChange={setClientId} />
              <Field label="Token URL" value={tokenUrl} onChange={setTokenUrl} />
              <div className="md:col-span-2">
                <Field label="SAML assertion" value={samlAssertion} onChange={setSamlAssertion} multiline />
              </div>
            </>
          ) : null}
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
