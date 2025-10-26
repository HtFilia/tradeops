import { FC, ReactNode } from "react";

interface ModuleCardProps {
  title: string;
  description: string;
  children?: ReactNode;
  badge?: string;
}

export const ModuleCard: FC<ModuleCardProps> = ({ title, description, children, badge }) => {
  return (
    <section className="module-card">
      <header className="module-card__header">
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
        {badge ? <span className="module-card__badge">{badge}</span> : null}
      </header>
      {children ? <div className="module-card__body">{children}</div> : null}
    </section>
  );
};
