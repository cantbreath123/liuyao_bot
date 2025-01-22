create table
  public.membership_tiers (
    id bigserial not null,
    tier_id character varying(64) not null,
    name character varying(64) not null,
    price numeric(10, 2) not null,
    daily_limit integer null,
    description text null,
    duration_unit character varying(50) not null,
    duration_amount integer not null,
    status boolean not null default true,
    env character varying(32) null,
    created_at timestamp with time zone null default current_timestamp,
    updated_at timestamp with time zone null default current_timestamp,
    constraint membership_tiers_pkey primary key (id)
  ) tablespace pg_default;

create table
  public.projects (
    id serial not null,
    project_id character varying(64) not null,
    user_id character varying(64) not null,
    env character varying(32) null,
    message_list jsonb null,
    created_at timestamp with time zone null default current_timestamp,
    updated_at timestamp with time zone null default current_timestamp,
    constraint projects_pkey primary key (id),
    constraint projects_project_id_key unique (project_id)
  ) tablespace pg_default;

 create table
  public.user_memberships (
    id bigserial not null,
    user_id character varying(64) not null,
    tier_id character varying(64) not null,
    start_time timestamp with time zone not null,
    end_time timestamp with time zone not null,
    status boolean not null default true,
    env character varying(32) null,
    created_at timestamp with time zone null default current_timestamp,
    updated_at timestamp with time zone null default current_timestamp,
    constraint user_memberships_pkey primary key (id)
  ) tablespace pg_default;

create table
  public.users (
    id serial not null,
    user_id character varying(64) not null,
    is_valid boolean null default true,
    created_at timestamp with time zone null default current_timestamp,
    updated_at timestamp with time zone null default current_timestamp,
    tg_user_id character varying null,
    constraint users_pkey primary key (id),
    constraint users_user_id_key unique (user_id)
  ) tablespace pg_default;
