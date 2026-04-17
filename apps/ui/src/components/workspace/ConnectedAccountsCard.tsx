import type { Health } from "../../types/domain";

type AccountInfo = {
  id: string;
  label: string;
  status: "connected" | "pending" | "disconnected";
  detail?: string;
};

function statusDot(status: AccountInfo["status"]) {
  const colors: Record<string, string> = {
    connected: "var(--accent)",
    pending: "var(--warning)",
    disconnected: "var(--text-muted)",
  };
  return (
    <span
      style={{
        display: "inline-block",
        width: 8,
        height: 8,
        borderRadius: "50%",
        background: colors[status] || colors.disconnected,
        flexShrink: 0,
      }}
    />
  );
}

function resolveStatus(flag: boolean | undefined): AccountInfo["status"] {
  if (flag === true) return "connected";
  if (flag === false) return "pending";
  return "disconnected";
}

export function ConnectedAccountsCard({ health }: { health: Health | null }) {
  if (!health) return null;

  const accounts: AccountInfo[] = [
    {
      id: "workspace",
      label: "Çalışma Klasörü",
      status: health.workspace_configured ? "connected" : "disconnected",
      detail: health.workspace_root_name || undefined,
    },
    {
      id: "provider",
      label: "Model Sağlayıcısı",
      status: health.provider_configured ? "connected" : "disconnected",
      detail: health.provider_model || health.provider_type || undefined,
    },
    {
      id: "gmail",
      label: "Gmail",
      status: resolveStatus(health.gmail_connected),
      detail: health.google_account_label || undefined,
    },
    {
      id: "google-calendar",
      label: "Google Takvim",
      status: resolveStatus(health.calendar_connected),
    },
    {
      id: "drive",
      label: "Google Drive",
      status: resolveStatus(health.drive_connected),
    },
    {
      id: "outlook-mail",
      label: "Outlook Mail",
      status: resolveStatus(health.outlook_mail_connected),
      detail: health.outlook_account_label || undefined,
    },
    {
      id: "outlook-calendar",
      label: "Outlook Takvim",
      status: resolveStatus(health.outlook_calendar_connected),
    },
    {
      id: "telegram",
      label: "Telegram",
      status: resolveStatus(health.telegram_configured),
      detail: health.telegram_bot_username || undefined,
    },
    {
      id: "whatsapp",
      label: "WhatsApp",
      status: resolveStatus(health.whatsapp_configured),
      detail: health.whatsapp_account_label || undefined,
    },
    {
      id: "x",
      label: "X",
      status: resolveStatus(health.x_configured),
      detail: health.x_account_label || undefined,
    },
  ];

  const connectedCount = accounts.filter((a) => a.status === "connected").length;

  return (
    <section className="hub-accounts">
      <div className="hub-accounts__header">
        <h2 className="hub-section-title">Bağlı Hesaplar</h2>
        <span className="hub-accounts__count">
          {connectedCount}/{accounts.length} aktif
        </span>
      </div>
      <div className="hub-accounts__grid">
        {accounts.map((account) => (
          <div key={account.id} className="hub-account-item">
            <div className="hub-account-item__top">
              {statusDot(account.status)}
              <span className="hub-account-item__label">{account.label}</span>
            </div>
            {account.detail ? (
              <span className="hub-account-item__detail">{account.detail}</span>
            ) : (
              <span className="hub-account-item__detail hub-account-item__detail--empty">
                {account.status === "disconnected" ? "Bağlı değil" : "Beklemede"}
              </span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
