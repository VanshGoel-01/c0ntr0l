CREATE TABLE IF NOT EXISTS control.organizations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text NOT NULL UNIQUE,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'archived')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (slug ~ '^[a-z0-9][a-z0-9-]{0,62}$')
);

CREATE TABLE IF NOT EXISTS control.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    external_subject text UNIQUE,
    email text,
    display_name text,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'deleted')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS control.organization_members (
    organization_id uuid NOT NULL
        REFERENCES control.organizations(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES control.users(id) ON DELETE CASCADE,
    role text NOT NULL DEFAULT 'member'
        CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    joined_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, user_id)
);

CREATE TABLE IF NOT EXISTS control.projects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL
        REFERENCES control.organizations(id) ON DELETE CASCADE,
    slug text NOT NULL,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived')),
    created_by_user_id uuid REFERENCES control.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_id, slug),
    CHECK (slug ~ '^[a-z0-9][a-z0-9-]{0,62}$')
);

CREATE TABLE IF NOT EXISTS control.applications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES control.projects(id) ON DELETE CASCADE,
    slug text NOT NULL,
    name text NOT NULL,
    environment text NOT NULL DEFAULT 'development'
        CHECK (environment IN ('development', 'test', 'staging', 'production')),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, slug),
    CHECK (slug ~ '^[a-z0-9][a-z0-9-]{0,62}$')
);

CREATE TABLE IF NOT EXISTS control.agents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id uuid NOT NULL
        REFERENCES control.applications(id) ON DELETE CASCADE,
    slug text NOT NULL,
    name text NOT NULL,
    agent_type text NOT NULL DEFAULT 'assistant',
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (application_id, slug),
    CHECK (slug ~ '^[a-z0-9][a-z0-9-]{0,62}$')
);

CREATE TABLE IF NOT EXISTS control.project_api_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES control.projects(id) ON DELETE CASCADE,
    name text NOT NULL,
    key_prefix text NOT NULL,
    key_hash text NOT NULL UNIQUE,
    is_active boolean NOT NULL DEFAULT true,
    last_used_at timestamptz,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, name),
    CHECK (length(key_prefix) BETWEEN 4 AND 24)
);

COMMENT ON COLUMN control.project_api_keys.key_hash IS
    'One-way hash only; raw API keys must never be stored';
