import aiohttp
import os
import re


class RepoConfig:
    public: str
    private: str
    fallback: str

    def __init__(self, subyaml: dict):
        self.public = subyaml.get("public", "/x1/repos/asf/")
        self.private = subyaml.get("private", "/x1/repos/private/")
        self.fallback = subyaml.get("fallback", "")
        assert isinstance(self.public, str) and os.path.isdir(self.public), "Public repo dir must exist!"
        assert isinstance(self.private, str) and os.path.isdir(self.private), "Private repo dir must exist!"


class Repository:
    private: bool
    filename: str
    filepath: str
    project: str
    description: str
    archived: bool

    def __init__(self, private, filepath):
        self.private = private
        self.filename = os.path.basename(filepath).replace('.git', '')
        self.filepath = filepath
        nocommit_file = os.path.join(filepath, "nocommit")
        desc_file = os.path.join(filepath, "description")
        self.archived = os.path.exists(nocommit_file)  # If a nocommit file exists within the .git dir, it is archived/read-only
        self.description = ""
        if os.path.isfile(desc_file):
            try:
                self.description = open(desc_file).read()
            except Exception:
                print(f"Could not read description of {filepath}, setting to blank")

        m = re.match(r"^(?:incubator-)?(empire-db|[^-.]+)-?.*(?:\.git)?$", self.filename)
        if m:
            self.project = m.group(1)
        else:
            self.project = self.filename.split('-', 1)[0]  # ????

    def __str__(self):
        return self.filename

    def __repr__(self):
        return f"Repository<{self.filepath}>"


async def list_all(cfg: RepoConfig) -> list:
    """ Fetches all local and fallback-via-remote repositories we host.

    :param cfg: Repository configuration object
    :return: A list of all repositories we manage, as Repository objects
    """
    repositories = []
    public_found = 0
    private_found = 0

    # Add public repos, should all be in one big directory
    for repo in [x for x in os.listdir(cfg.public) if x.endswith('.git')]:
        public_found += 1
        filepath = os.path.join(cfg.public, repo)
        repositories.append(Repository(False, filepath))

    # Add private repos, should be in individual sub dirs, one per project
    for project in os.listdir(cfg.private):
        path = os.path.join(cfg.private, project)
        for repo in [x for x in os.listdir(path) if x.endswith('.git')]:
            filepath = os.path.join(cfg.private, project, repo)
            private_found += 1
            repositories.append(Repository(True, filepath))

    # If fallback from old server, add those into the mix
    if cfg.fallback:
        async with aiohttp.ClientSession() as session:
            async with session.get(cfg.fallback) as rv:
                data = await rv.text()
                for repo in sorted(data.split("\n")):
                    public_found += 1
                    repositories.append(Repository(False, repo))
    print(f"Located {len(repositories)} repositories ({public_found} public, {private_found} private)")
    return repositories
