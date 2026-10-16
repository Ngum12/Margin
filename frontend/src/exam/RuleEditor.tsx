import { useTranslation } from "react-i18next";
import type { PointRules, PointGroup } from "../api/types";
import { Field } from "../components/ui";

const defaults: PointRules = {
  key: "",
  reject: [],
  kind: "point",
  depends_on: [],
  ecf: false,
  ecf_from: "",
  meaning_based: true,
  teacher_only: false,
  group: "",
};
export function RuleEditor({
  rules,
  onChange,
}: {
  rules?: PointRules | undefined;
  onChange: (r: PointRules) => void;
}) {
  const { t } = useTranslation();
  const value = rules ?? defaults;
  const change = (patch: Partial<PointRules>) => {
    onChange({ ...value, ...patch });
  };
  return (
    <details>
      <summary>
        {t("schemeRules.title")}
        {value.teacher_only ? ` · ${t("schemeRules.teacher_only")}` : ""}
      </summary>
      <Field label={t("schemeRules.key")}>
        <input
          value={value.key}
          maxLength={40}
          onChange={(e) => {
            change({ key: e.target.value });
          }}
        />
      </Field>
      <Field label={t("schemeRules.kind")}>
        <select
          value={value.kind}
          onChange={(e) => {
            change({ kind: e.target.value as PointRules["kind"] });
          }}
        >
          {["point", "M", "A", "B"].map((kind) => (
            <option key={kind} value={kind}>
              {t(`schemeRules.kinds.${kind}`)}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("schemeRules.reject")}>
        <textarea
          value={value.reject.join("\n")}
          onChange={(e) => {
            change({ reject: e.target.value.split("\n") });
          }}
        />
      </Field>
      <Field label={t("schemeRules.depends")}>
        <input
          value={value.depends_on.join(",")}
          onChange={(e) => {
            change({
              depends_on: e.target.value
                .split(",")
                .map((x) => x.trim())
                .filter(Boolean),
            });
          }}
        />
      </Field>
      <Field label={t("schemeRules.group")}>
        <input
          value={value.group}
          onChange={(e) => {
            change({ group: e.target.value });
          }}
        />
      </Field>
      {(["ecf", "meaning_based", "teacher_only"] as const).map((key) => (
        <label key={key} className="checkbox">
          <input
            type="checkbox"
            checked={value[key]}
            onChange={(e) => {
              change({ [key]: e.target.checked });
            }}
          />
          {t(`schemeRules.${key}`)}
        </label>
      ))}
      {value.ecf && (
        <Field label={t("schemeRules.ecf_from")}>
          <input
            value={value.ecf_from}
            onChange={(e) => {
              change({ ecf_from: e.target.value });
            }}
          />
        </Field>
      )}
    </details>
  );
}
export function GroupEditor({
  groups,
  onChange,
}: {
  groups: PointGroup[];
  onChange: (g: PointGroup[]) => void;
}) {
  const { t } = useTranslation();
  return (
    <details>
      <summary>{t("schemeRules.groups")}</summary>
      {groups.map((g, i) => (
        <div className="form-row" key={i}>
          <Field label={t("schemeRules.group")}>
            <input
              value={g.key}
              onChange={(e) => {
                onChange(groups.map((x, n) => (n === i ? { ...x, key: e.target.value } : x)));
              }}
            />
          </Field>
          <Field label={t("schemeRules.any")}>
            <input
              type="number"
              min={1}
              max={50}
              value={g.max_points}
              onChange={(e) => {
                onChange(
                  groups.map((x, n) =>
                    n === i ? { ...x, max_points: Number(e.target.value) } : x,
                  ),
                );
              }}
            />
          </Field>
          <Field label={t("editor.maxMarks")}>
            <input
              type="number"
              min={1}
              max={100}
              value={g.max_marks}
              onChange={(e) => {
                onChange(
                  groups.map((x, n) => (n === i ? { ...x, max_marks: Number(e.target.value) } : x)),
                );
              }}
            />
          </Field>
          <button
            type="button"
            className="button-quiet"
            onClick={() => {
              onChange(groups.filter((_, n) => n !== i));
            }}
          >
            {t("common.remove")}
          </button>
        </div>
      ))}
      <button
        type="button"
        className="button-secondary"
        onClick={() => {
          onChange([
            ...groups,
            { key: `group${String(groups.length + 1)}`, max_points: 1, max_marks: 1 },
          ]);
        }}
      >
        {t("schemeRules.addGroup")}
      </button>
    </details>
  );
}
