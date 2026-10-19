-- Remove the OpenAI key that every project config stored until now.
--
-- LLMConfig.api_key was filled from the server's settings and serialised
-- with the rest of the config, so it sat in every row and came back to the
-- browser in the project response. The field is now excluded from dumps;
-- this takes it out of the rows already written. Idempotent: `#-` on a
-- missing path is a no-op, and the where clause keeps reruns from touching
-- anything.

update projects
   set config = config #- '{llm,api_key}'
 where config -> 'llm' ? 'api_key';
