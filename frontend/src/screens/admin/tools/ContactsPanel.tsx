import { useCallback, useState } from "react";
import {
  archiveOrganizationContact,
  createOrganizationContact,
  describeActionError,
  fetchOrganizationContacts,
} from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { useAsync } from "../../../hooks/useAsync";

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.5rem",
  borderRadius: "0.5rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
} as const;

const EMPTY_FORM = {
  organization_name: "",
  contact_name: "",
  position: "",
  email: "",
  phone: "",
  notes: "",
};

// Mini App equivalent of the bot's "🤝 База организаций" flow
// (app/handlers/admin/management_ready.py) — see app/services/admin_contacts_service.py.
// Second-contact fields exist on the model but aren't exposed here, matching
// the bot's own pipe-delimited form which always let admins skip them.
export function ContactsPanel() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchOrganizationContacts(), [refreshKey]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const handleCreate = useCallback(async () => {
    if (!form.organization_name.trim()) return;
    setCreating(true);
    setActionError(null);
    try {
      await createOrganizationContact({
        organization_name: form.organization_name.trim(),
        contact_name: form.contact_name.trim() || null,
        position: form.position.trim() || null,
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        notes: form.notes.trim() || null,
      });
      setForm(EMPTY_FORM);
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [form, refresh]);

  const handleArchive = useCallback(
    async (contactId: number) => {
      setBusyId(contactId);
      setActionError(null);
      try {
        await archiveOrganizationContact(contactId);
        refresh();
      } catch (error) {
        setActionError(describeActionError(error));
      } finally {
        setBusyId(null);
      }
    },
    [refresh],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {actionError && (
        <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{actionError}</p>
      )}
      <Card>
        <strong>Новая организация</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
          <input
            placeholder="Название организации"
            value={form.organization_name}
            onChange={(e) => setForm({ ...form, organization_name: e.target.value })}
            style={inputStyle}
          />
          <input
            placeholder="Контактное лицо"
            value={form.contact_name}
            onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
            style={inputStyle}
          />
          <input
            placeholder="Должность"
            value={form.position}
            onChange={(e) => setForm({ ...form, position: e.target.value })}
            style={inputStyle}
          />
          <input
            placeholder="Почта"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            style={inputStyle}
          />
          <input
            placeholder="Телефон"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
            style={inputStyle}
          />
          <textarea
            placeholder="Заметка"
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            rows={2}
            style={inputStyle}
          />
          <button
            type="button"
            className="era-btn-primary"
            disabled={creating || !form.organization_name.trim()}
            onClick={handleCreate}
          >
            Добавить организацию
          </button>
        </div>
      </Card>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить организации." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Пока контактов нет." />}
      {state.status === "ready" &&
        state.data.map((contact) => (
          <Card key={contact.id}>
            <strong>{contact.organization_name}</strong>
            <p style={{ margin: "0.25rem 0 0.5rem", color: "var(--era-text-muted)" }}>
              {contact.contact_name ?? "Контакт не указан"} · {contact.position ?? "должность не указана"}
              <br />
              {[contact.email, contact.phone].filter(Boolean).join(" · ")}
            </p>
            <button type="button" disabled={busyId === contact.id} onClick={() => handleArchive(contact.id)}>
              Скрыть
            </button>
          </Card>
        ))}
    </div>
  );
}
