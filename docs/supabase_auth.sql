create table if not exists public.users (
  username text primary key,
  email text not null unique,
  password_hash text not null,
  created_at bigint not null,
  updated_at bigint not null
);

alter table public.users enable row level security;

drop policy if exists "service role manages users" on public.users;
create policy "service role manages users"
on public.users
for all
using (auth.role() = 'service_role')
with check (auth.role() = 'service_role');
