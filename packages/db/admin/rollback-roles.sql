\set ON_ERROR_STOP on

\if :{?owner_role}
\else
  \echo 'owner_role is required, for example: -v owner_role=postgres'
  \quit 2
\endif

BEGIN;

\if :{?web_login}
SELECT format('REVOKE deedleague_web FROM %I', :'web_login') \gexec
\endif
\if :{?pipeline_login}
SELECT format('REVOKE deedleague_pipeline FROM %I', :'pipeline_login') \gexec
\endif
\if :{?migrator_login}
SELECT format('REVOKE deedleague_migrator FROM %I', :'migrator_login') \gexec
\endif

REASSIGN OWNED BY deedleague_migrator TO :"owner_role";
DROP OWNED BY deedleague_web;
DROP OWNED BY deedleague_pipeline;
DROP OWNED BY deedleague_migrator;

DROP ROLE deedleague_web;
DROP ROLE deedleague_pipeline;
DROP ROLE deedleague_migrator;

COMMIT;
