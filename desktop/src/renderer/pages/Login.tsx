import { useEffect, useState, type FormEvent } from "react";
import { CaretDown, CaretUp } from "@phosphor-icons/react";
import { useApp } from "../app/context";
import { useAction } from "../app/hooks";
import { Button, Field, Modal, Notice } from "../components/ui";
import logo from "../assets/logo.png";

export function LoginPage() {
  const { service, navigate, refreshSession } = useApp();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [trial, setTrial] = useState("");
  const [trialOpen, setTrialOpen] = useState(false);
  const [tokenOpen, setTokenOpen] = useState(false);
  const [token, setToken] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [cooldown, setCooldown] = useState(0);
  const [information, setInformation] = useState<string | null>(null);
  const login = useAction();
  const sms = useAction();
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((n) => n - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);
  const validPhone = () => {
    if (!/^1\d{10}$/.test(phone.trim())) {
      setErrors({ phone: "请输入 11 位手机号码。" });
      return false;
    }
    setErrors({});
    return true;
  };
  const requestCode = async () => {
    if (!validPhone() || cooldown > 0) return;
    const result = await sms.run(() => service.requestCode(phone.trim()));
    if (result) setCooldown(Math.max(1, Math.min(300, result.retryAfter)));
  };
  const finish = async (authenticated: boolean) => {
    if (!authenticated) {
      login.setError("登录尚未完成，请核对凭证后重试。");
      return;
    }
    setCode("");
    setToken("");
    await refreshSession();
    navigate("/workbench");
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!validPhone()) return;
    if (!/^\d{6}$/.test(code)) {
      setErrors({ code: "请输入 6 位短信验证码。" });
      return;
    }
    if (trialOpen && !trial.trim()) {
      setErrors({ trial: "请输入试用码，或收起试用开通。" });
      return;
    }
    const result = await login.run(() =>
      service.login(phone.trim(), code, trialOpen ? trial.trim() : undefined),
    );
    if (result) await finish(result.authenticated);
  };
  const submitToken = async (event: FormEvent) => {
    event.preventDefault();
    if (!token.trim()) {
      setErrors({ token: "请输入已有访问凭证。" });
      return;
    }
    setErrors({});
    const result = await login.run(() => service.loginToken(token.trim()));
    if (result) await finish(result.authenticated);
  };
  return (
    <main className="login-layout">
      <section className="login-brand" aria-label="意客 AI">
        <div className="login-wordmark">
          <img src={logo} alt="" />
          <span>意客AI</span>
        </div>
        <h1>找到值得联系的新需求</h1>
        <p>找需求 · 看证据 · 跟进联系</p>
      </section>
      <section className="login-panel" aria-labelledby="login-title">
        <h2 id="login-title">欢迎使用意客AI</h2>
        <p className="page-description">登录后开启商机发现与跟进工作</p>
        <form onSubmit={submit} noValidate>
          <Field label="手机号码" required error={errors.phone}>
            <input
              aria-label="手机号码"
              type="tel"
              autoComplete="tel"
              inputMode="tel"
              maxLength={11}
              placeholder="请输入手机号码"
              value={phone}
              onChange={(e) => {
                setPhone(e.target.value);
                setErrors({});
                sms.setError("");
              }}
            />
          </Field>
          <Field label="短信验证码" required error={errors.code}>
            <div className="login-code-row">
              <input
                aria-label="短信验证码"
                type="password"
                autoComplete="one-time-code"
                inputMode="numeric"
                maxLength={6}
                placeholder="请输入验证码"
                value={code}
                onChange={(e) => {
                  setCode(e.target.value);
                  setErrors({});
                }}
              />
              <Button
                onClick={() => void requestCode()}
                loading={sms.busy}
                disabled={cooldown > 0}
              >
                {cooldown > 0 ? `${cooldown} 秒后重试` : "获取验证码"}
              </Button>
            </div>
          </Field>
          {sms.error && <Notice tone="error">{sms.error}</Notice>}
          {trialOpen && (
            <Field label="试用码" required error={errors.trial}>
              <input
                aria-label="试用码"
                autoComplete="off"
                maxLength={128}
                placeholder="请输入试用码"
                value={trial}
                onChange={(e) => {
                  setTrial(e.target.value);
                  setErrors({});
                }}
              />
            </Field>
          )}
          {!tokenOpen && login.error && (
            <Notice tone="error">{login.error}</Notice>
          )}
          <Button
            type="submit"
            variant="primary"
            className="login-submit"
            loading={login.busy}
          >
            登录
          </Button>
          <Button
            variant="ghost"
            className="login-expand"
            aria-expanded={trialOpen}
            onClick={() => {
              setTrialOpen(!trialOpen);
              setErrors({});
            }}
          >
            {trialOpen ? <CaretUp /> : <CaretDown />}首次使用，输入试用码开通
          </Button>
        </form>
        <div className="login-token">
          <Button
            variant="ghost"
            aria-expanded={tokenOpen}
            onClick={() => {
              setTokenOpen(!tokenOpen);
              setToken("");
              setErrors({});
              login.setError("");
            }}
          >
            使用已有访问凭证 {tokenOpen ? <CaretUp /> : <CaretDown />}
          </Button>
          {tokenOpen && (
            <form onSubmit={submitToken} noValidate>
              <Field
                label="短期访问凭证"
                required
                error={errors.token}
                hint="使用已开通客户空间的短期凭证登录。"
              >
                <input
                  aria-label="短期访问凭证"
                  type="password"
                  autoComplete="off"
                  maxLength={8192}
                  value={token}
                  placeholder="粘贴已有访问凭证"
                  onChange={(e) => {
                    setToken(e.target.value);
                    setErrors({});
                  }}
                />
              </Field>
              {login.error && <Notice tone="error">{login.error}</Notice>}
              <Button type="submit" variant="primary" loading={login.busy}>
                使用凭证登录
              </Button>
            </form>
          )}
        </div>
        <footer className="login-footer">
          {["用户协议", "隐私政策", "联系支持"].map((title) => (
            <Button
              key={title}
              variant="ghost"
              onClick={() => setInformation(title)}
            >
              {title}
            </Button>
          ))}
        </footer>
      </section>
      {information && (
        <Modal
          title={information}
          onClose={() => setInformation(null)}
          footer={<Button onClick={() => setInformation(null)}>关闭</Button>}
        >
          <p>
            {information === "联系支持"
              ? "请联系为你开通客户空间的服务方。可在账号与授权中获取不包含凭证的诊断信息。"
              : "本构建尚未配置正式文件。请向服务方取得并阅读相应文件后使用客户服务。"}
          </p>
        </Modal>
      )}
    </main>
  );
}
