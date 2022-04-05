let gh_org = "apache";
let gh_client_id = '6f70292dcb4d00b5f537';
let state = Math.random().toString(20).substr(2, 6) + Math.random().toString(20).substr(2, 6) + Math.random().toString(20).substr(2, 6);
let hostname = location.hostname;


let txt = (a) => document.createTextNode(a);
let br = (a) => document.createElement('br');
let h2 = (a) => {let x = document.createElement('h2'); x.innerText = a ? a : ""; return x}
let h1 = (a) => {let x = document.createElement('h1'); x.innerText = a ? a : ""; return x}

let login_cached = {};

function blurbg(blur = false) {
    if (blur) document.body.setAttribute("class", "blurbg");
    else  document.body.setAttribute("class", "");
}

async function POST(url = '', data = {}) {
    const response = await fetch(url, {
        method: 'POST',
        mode: 'cors',
        cache: 'no-cache',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json'
        },
        redirect: 'follow',
        referrerPolicy: 'no-referrer',
        body: JSON.stringify(data)
    });
    return response.json();
}

async function GET(url = '') {

    let js = fetch(url, {
        method: 'GET',
        mode: 'cors',
        cache: 'no-cache',
        credentials: 'same-origin',
        redirect: 'follow',
        referrerPolicy: 'no-referrer',
    }).then((response) => response.json()).catch(() => {
            let canvas = document.getElementById('main');
            canvas.innerHTML = "";
            canvas.innerText = "There was a problem contacting the Boxer backend service, please try again. If this problem persists, please inform ASF Infrastructure at: users@infra.apache.org";
        }
    );
    return js
}

function logout() {
    GET("api/preferences?logout=true").then(() => location.href = '/');
}

function check_github_invite(canvas) {
    GET("api/preferences.json").then((js) => {
        if (js.credentials.github_org_member) {
            canvas.innerText = "GitHub organization invite recorded! Hang tight, we're loading things for you...";
            window.setTimeout(() => { location.search = ''; location.reload();}, 4000);
        } else {
            window.setTimeout(() => { check_github_invite(canvas); }, 10000);
        }
    });
}


function invite_github(canvas) {
    GET("api/invite").then(
        (js) => {
            if (js.okay) {
                canvas.innerHTML = "";
                init_step(canvas, 2)
                canvas.appendChild(h2("GitHub Organization Membership"))
                canvas.appendChild(txt("An invitation has been sent to your email address. You may also review it here: "));
                let a = document.createElement("a");
                a.setAttribute("href", `https://github.com/orgs/${gh_org}/invitation`);
                a.setAttribute("target", "_new");
                a.innerText = "Review invitation";
                canvas.appendChild(a);
                let p = document.createElement('p');
                p.appendChild(txt("Once you have accepted your invitation, the Boxer service will start including you in the teams you have been assigned to. "));
                p.appendChild(br());
                p.appendChild(txt("It may take up to five minutes before this happens. This page will reload once your invitation has been recorded as accepted, sit tight..."));
                canvas.appendChild(p);
                let loader = document.createElement('div');
                loader.setAttribute('class', 'loader');
                canvas.appendChild(loader);
                check_github_invite(canvas);
            } else {
                if (js.reauth === true) {
                    canvas.innerText = "It looks like something went wrong with the invitation. You have likely previously been a member of the organization and then left. To fix this, we'll need to re-authenticate you on GitHub. Please hang on while we sort that out....";
                    window.setTimeout(() => { location.search = ''; location.reload();}, 3000);
                }
                else {
                    canvas.innerText = "Oops! Something went wrong, you may already have an invitation pending."
                }
            }
        }
    )
}

function unlink_github() {
    if (confirm("Are you sure you wish to unlink your GitHub account? You will lose all GitHub write-access on your current account if so. You may re-link this or another account once you have unlinked.")) {
        GET("api/invite?unlink=true").then(() => {
            alert("Your GitHub account has been unlinked. Please re-authenticate to link to a new or previous GitHub account.");
            location.reload();
        })
    }
}


function show_page_profile(canvas, login) {
    canvas.innerText = "";
    init_step(canvas, 5);

    let card = document.createElement('div');
    card.setAttribute('id', "card");

    let avatar = document.createElement('img');
    avatar.setAttribute('src', `https://github.com/${login.github.login}.png`);
    avatar.setAttribute('class', 'avatar');
    card.appendChild(avatar);

    let name = document.createElement('h1');
    name.innerText = login.credentials.fullname;
    card.appendChild(name);

    card.appendChild(document.createElement('hr'));

    let boxerstatus = document.createElement('table');
    boxerstatus.style.border = "none";
    boxerstatus.style.width = "95%"

    // ASF Auth
    if (login.credentials.uid) {
        let tr = document.createElement('tr');
        let icon = document.createElement('td');
        icon.style.textAlign = 'center';
        let iconimg = document.createElement('img');
        iconimg.setAttribute('src', 'images/asf.png');
        iconimg.style.height = '24px';
        icon.appendChild(iconimg);
        let xtxt = document.createElement('td');
        xtxt.innerText = `Authenticated at ASF as: ${login.credentials.uid}`;
        tr.appendChild(icon);
        tr.appendChild(xtxt);
        boxerstatus.appendChild(tr);
    }

    // GitHub Auth
    if (login.github.login) {
        let tr = document.createElement('tr');
        let icon = document.createElement('td');
        icon.style.textAlign = 'center';
        let iconimg = document.createElement('img');
        iconimg.setAttribute('src', 'images/github.png');
        iconimg.style.height = '24px';
        icon.appendChild(iconimg);
        let xtxt = document.createElement('td');
        xtxt.innerText = `Authenticated at GitHub as: ${login.github.login} (`;
        let unlink = document.createElement('a');
        unlink.setAttribute('href', '#');
        unlink.innerText = "unlink account";
        unlink.addEventListener('click', unlink_github);
        xtxt.appendChild(unlink);
        xtxt.appendChild(txt(")"));
        tr.appendChild(icon);
        tr.appendChild(xtxt);
        boxerstatus.appendChild(tr);
    }


    card.appendChild(boxerstatus);

    canvas.appendChild(card);

    if (login.github.mfa) {
        if (login.github.repositories.length > 0) {
            let ul = document.createElement('ul');
            ul.setAttribute('class', 'striped');
            canvas.appendChild(ul);
            ul.innerText = "You have write access to the following repositories:";
            login.github.repositories.sort();
            for (let i = 0; i < login.github.repositories.length; i++) {
                let repo = login.github.repositories[i];
                const ghlink = `https://github.com/${gh_org}/${repo}`;
                let gblink = `https://gitbox.apache.org/repos/asf/${repo}.git`;
                let private = false;
                if (login.github.private.includes(repo)) {
                    private = true;
                    let m = repo.match(/^(?:incubator-)?(empire-db|[^-.]+)-?.*/);
                    if (m) {
                        const project = m[1];
                        gblink = `https://gitbox.apache.org/repos/private/${project}/${repo}.git`;
                    }
                }
                const repospan = document.createElement('span');
                repospan.style.display = "inline-block";
                repospan.style.width = "480px";
                repospan.innerText = repo + ".git";
                repospan.style.color = private ? "red" : "black";
                const gha = document.createElement('a');
                gha.style.marginLeft = "20px";
                gha.setAttribute("href", ghlink);
                gha.setAttribute("target", "_blank");
                gha.innerText = "GitHub";
                const gba = document.createElement('a');
                gba.style.marginLeft = "20px";
                gba.setAttribute("href", gblink);
                gba.setAttribute("target", "_blank");
                gba.innerText = "GitBox";
                const visispan = document.createElement('span');
                visispan.style.marginLeft = "20px";
                visispan.style.display = "inline-block";
                visispan.innerText = private ? "Private repository" : "Public repository";
                visispan.style.color = private ? "red" : "black";
                const li = document.createElement('li');
                li.appendChild(repospan);
                li.appendChild(gha);
                li.appendChild(gba);
                li.appendChild(visispan);
                ul.appendChild(li);
            }
        } else {
            canvas.appendChild(document.createTextNode("You do not appear to have access to any git repositories right now.\nIf you just linked your accounts, please allow a few minutes for the system to register your new repository access list."));
        }
    } else {
        canvas.appendChild(document.createTextNode("You need to enable multi-factor authentication at GitHub to get write access to repositories there."));
        let a = document.createElement('a');
        a.setAttribute('href', 'https://github.com/settings/security');
        a.setAttribute('target', '_new');
        a.innerText = "GitHub Account Security";
        canvas.appendChild(document.createElement('br'));
        canvas.appendChild(document.createTextNode("Please follow this link to set it up: "));
        canvas.appendChild(a);
        canvas.appendChild(document.createElement('br'));
        canvas.appendChild(document.createTextNode("It may take up to five minutes for Boxer to recognize your MFA being enabled."));
    }
}

function init_step(canvas, step) {
    canvas.innerHTML = "";
    let header = document.createElement('h1');
    header.style.textAlign = "center";
    header.style.width = "100%";
    let verified = document.createElement('img');
    verified.setAttribute('src', `images/v_step${step}.png`);
    verified.style.width = "600px";
    header.appendChild(verified);
    canvas.appendChild(header);
}



// Step one in setup: Auth with GitHub
function setup_step_one_github_auth(canvas, login) {
    init_step(canvas, 1);
    canvas.appendChild(h2("Authenticate on GitHub"));
    canvas.appendChild(txt("Please authenticate yourself on GitHub to proceed. This will ensure we know who you are in GitHub, and can invite you to the organization in case you are not a part of Apache on GitHub yet: "));
    canvas.appendChild(document.createElement('br'));
    let a = document.createElement("button");
    a.addEventListener("click", begin_oauth_github);
    a.innerText = "Authenticate with GitHub";
    canvas.appendChild(a);
}

// Step two in setup: Invite to GitHub Org
function setup_step_two_github_org(canvas, login) {
    init_step(canvas, 2);
    canvas.appendChild(h2("GitHub Organization Membership"));
    canvas.appendChild(txt("You do not appear to be a part of the Apache GitHub organization yet. "));
    canvas.appendChild(document.createElement('br'));
    canvas.appendChild(document.createElement('br'));
    let a = document.createElement("button");
    a.addEventListener("click", () => invite_github(canvas));
    a.innerText = "Send GitHub Invitation!";
    canvas.appendChild(document.createTextNode('Click this button to receive an invitation so you can gain write-access on GitHub: '));
    canvas.appendChild(a);
}

// Step three in setup: verify MFA
function setup_step_three_mfa(canvas, login) {
    canvas.innerHTML = "";
    init_step(canvas, 3)
    canvas.appendChild(h2("Multi-factor Authentication Check"))
    canvas.appendChild(txt("You do not appear to have enabled Multi-factor Authentication (MFA) on GitHub yet. "));
    canvas.appendChild(br());
    canvas.appendChild(txt("Please enable this and reload this page, as we cannot grant write access to GitHub repositories to accounts without MFA enabld."));
    canvas.appendChild(br());
    canvas.appendChild(txt("If you already have MFA enabled, it may take up to five minutes for the Boxer service to recognize it."));
}


let search_timer = null;
let search_query = "";
let previous_query = "";

async function search_fetch(obj) {
    if (search_query == previous_query) return;
    previous_query = search_query;
    obj.innerHTML = "";
    let res = await GET('api/users.json?query=' + search_query);
    history.pushState({}, "Search Results", '?action=search&query=' + search_query);
    if (res.results) {
        if (res.results.length == 0) {
            obj.innerText = `No results matching ${search_query} could be found.`;
        }
        for (let i = 0; i < res.results.length; i++) {
            let result = res.results[i];
            let tr = document.createElement('tr');

            let td;
            // ASF ID
            td = document.createElement('td');
            td.innerText = result.asf_id;
            tr.appendChild(td);

            // GitHub ID
            td = document.createElement('td');
            td.innerText = result.github_id;
            tr.appendChild(td);

            // GitHub MFA
            td = document.createElement('td');
            td.style.textAlign = 'center';
            let img = document.createElement('img');
            img.style.height = "16px";
            if (result.github_mfa) {
                img.setAttribute('src', 'images/mfa_enabled.png');
            } else {
                img.setAttribute('src', 'images/mfa_disabled.png');
            }
            td.appendChild(img);
            tr.appendChild(td);

            // GitHub repos
            td = document.createElement('td');
            td.style.textAlign = 'right';
            td.innerText = result.repositories.length;
            tr.appendChild(td);

            // GitHub status
            td = document.createElement('td');
            td.innerText = "Accounts linked";
            if (!result.github_id || result.github_id.length == 0) {
                td.innerHTML = "Not authed on GitHub <sup>[1]</sup>";
            }
            else if (result.github_invited == false) {
                td.innerHTML = "Not part of GiHub org <sup>[2]</sup>";
            } else if (result.github_mfa == false) {
                td.innerHTML= "MFA not enabled on GitHub <sup>[3]</sup>";
            }
            tr.appendChild(td);

            obj.appendChild(tr);
        }
    }
}

function search_result(obj, val) {
    if (search_timer) {
        window.clearTimeout(search_timer);
    }
    search_query = val;
    search_timer = window.setTimeout(() => search_fetch(obj), 250);
}


function search_page(canvas, query) {
    canvas.innerHTML = "";
    let header = h1("User search");
    canvas.appendChild(header);
    let inp = document.createElement('input');
    inp.setAttribute('placeholder', "Enter an Apache or GitHub ID");
    inp.value = query;
    canvas.appendChild(inp);
    let table = document.createElement('table');
    table.setAttribute('class', 'striped');

    let tr = document.createElement('tr');
    let th;
    th = document.createElement('th');
    th.innerText = "Apache ID";
    tr.appendChild(th);
    th = document.createElement('th');
    th.innerText = "GitHub ID";
    tr.appendChild(th);
    th = document.createElement('th');
    th.innerText = "MFA";
    tr.appendChild(th);
    th = document.createElement('th');
    th.innerText = "Repos";
    tr.appendChild(th);
    th = document.createElement('th');
    th.innerText = "Status";
    tr.appendChild(th);
    table.appendChild(tr);
    let results = document.createElement('tbody');
    table.appendChild(results);
    canvas.appendChild(table);
    inp.addEventListener('keyup', (x) => search_result(results, x.target.value));
    if (query && query.length) {
        search_result(results, query);
    }

    let p = document.createElement('p');
    p.innerText = "Detailed debugging help:";
    canvas.appendChild(p);
    let ul = document.createElement('ul');
    ul.setAttribute('class', 'striped');
    ul.style.maxWidth = "800px";
    let li;

    li = document.createElement('li');
    li.innerText = "[0] Accounts linked: All is good, nothing to do here.";
    ul.append(li);

    li = document.createElement('li');
    li.innerText = "[1] Not authed on GitHub: The user exists in LDAP, but has not used the Boxer app to authenticate with GitHub yet (so we don't know their GitHub login). To fix, the user should use boxer to authenticate with GitHub and follow the remaining steps.";
    ul.append(li);

    li = document.createElement('li');
    li.innerText = `[2] Not part of GiHub org: The user has completed the ASF and GitHub OAuth steps, but have not been invited to the ASF GitHub organization yet, or have not accepted the invitation. User should check https://github.com/orgs/${gh_org}/invitation for a pending invite, or follow the boxer guide to sending an invitation.`;
    ul.append(li);

    li = document.createElement('li');
    li.innerText = "[3] MFA not enabled: The user is a part of the Apache GitHub organization, but has not enabled Multi-Factor Authentication yet. This is a required step in order to gain write-access.";
    ul.append(li);

    canvas.appendChild(ul);

}

function kvpair(a, b) {
    let maindiv = document.createElement('div');
    let adiv = document.createElement('div');
    let bdiv = document.createElement('div');
    maindiv.style.width = "500px";
    adiv.style.width = "300px";
    bdiv.style.width = "200px";
    adiv.style.display = "inline-block";
    bdiv.style.display = "inline-block";
    adiv.appendChild(a);
    bdiv.appendChild(b);
    maindiv.appendChild(adiv);
    maindiv.appendChild(bdiv);
    return maindiv
}


function new_repo_prompt(canvas, login) {
    canvas.innerText = '';

    let title = document.createElement('h2');
    title.innerText = "Create a git repository:";
    canvas.appendChild(title);

    // Project dropdown
    let sel = document.createElement('select');
    sel.setAttribute('id', 'project');
    sel.setAttribute("onchange", "prep_new_repo(true);")
    let dl = document.createElement('option');
    dl.innerText = "--- Select a project ---";
    dl.disabled = false;
    dl.value = "";
    sel.appendChild(dl);
    for (let project of login.all_projects) {
        let disabled = true;
        if (login.credentials.admin || login.pmcs.includes(project)) {
            disabled = false;
        }
        let l = document.createElement('option');
        l.innerText = project;
        l.disabled = disabled;
        sel.appendChild(l);
    }
    let label = document.createElement('label');
    label.setAttribute("for", "project");
    label.innerText = "Project: ";
    canvas.appendChild(kvpair(label, sel));


    // Suffix?
    canvas.appendChild(br());
    let suffix = document.createElement('input');
    suffix.setAttribute("type" , "text");
    suffix.setAttribute("id" , "suffix");
    suffix.setAttribute("onkeyup", "prep_new_repo();")
    label = document.createElement('label');
    label.setAttribute("for", "suffix");
    label.innerText = "Optional repo sub-name: ";
    canvas.appendChild(kvpair(label, suffix));

    // Private?
    if (login_cached.credentials.admin) {
        canvas.appendChild(br());
        let priv = document.createElement('input');
        priv.setAttribute("type" , "checkbox");
        priv.setAttribute("id" , "private");
        priv.setAttribute("onchange", "prep_new_repo();")
        label = document.createElement('label');
        label.style.color = 'maroon';
        label.setAttribute("for", "private");
        label.innerText = "Make repository private*: ";
        canvas.appendChild(kvpair(label, priv));
    }

    // Commit mail target
    canvas.appendChild(br());
    let commit = document.createElement('input');
    commit.setAttribute("type" , "text");
    commit.style.width = "200px";
    commit.setAttribute("id" , "commit");
    commit.setAttribute("onkeyup", "prep_new_repo();")
    label = document.createElement('label');
    label.setAttribute("for", "commit");
    label.innerText = "Commit mailing list target: ";
    canvas.appendChild(kvpair(label, commit));

    // Dev mail target
    canvas.appendChild(br());
    let dev = document.createElement('input');
    dev.setAttribute("type" , "text");
    dev.setAttribute("id" , "dev");
    dev.style.width = "200px";
    dev.setAttribute("onkeyup", "prep_new_repo();")
    label = document.createElement('label');
    label.setAttribute("for", "dev");
    label.innerText = "Issue/PR mailing list target: ";
    canvas.appendChild(kvpair(label, dev));


    // Repo result
    canvas.appendChild(br());
    let final_repo_name = document.createElement('div');
    final_repo_name.style.padding = '10px'
    final_repo_name.style.color = 'blue'
    final_repo_name.setAttribute("id", "final_repo_name");
    canvas.appendChild(final_repo_name);

    // Submit button
    let sbmt = document.createElement('input');
    sbmt.setAttribute("type" ,"submit");
    sbmt.setAttribute("id" ,"sbmt");
    sbmt.setAttribute("onclick" ,"prep_new_repo(false, true);");
    sbmt.disabled = true;
    sbmt.value = "Create repository";
    let txt = document.createTextNode('');
    canvas.appendChild(kvpair(txt, sbmt));

    if (login_cached.credentials.admin) {
        canvas.appendChild(br());
        let privwarn = document.createElement('p');
        privwarn.style.fontSize = "0.75rem"
        privwarn.innerText = "*Private repositories are only visible to the (P)PMC of a project. This applies to both gitbox and github";
        canvas.appendChild(privwarn)
        canvas.appendChild(br());
    }

    canvas.appendChild(br());
    let a = document.createElement('a');
    a.setAttribute("href" , "https://s.apache.org/asfyaml");
    a.setAttribute("target" , "_blank");
    a.innerText = ".asf.yaml";
    canvas.appendChild(document.createTextNode("You may fine tune these settings later using "));
    canvas.appendChild(a);
    canvas.appendChild(document.createTextNode(" in the main branch of your repository."));
}


function prep_new_repo(refresh=false, submit=false) {
    let frn = document.getElementById('final_repo_name');
    let project = document.getElementById('project').value;
    let suffix = document.getElementById('suffix').value;
    let priv = login_cached.credentials.admin ? document.getElementById('private').checked : false;
    let repo_title = 'Apache ' + project;
    let repo_commit = document.getElementById('commit').value;
    let repo_dev = document.getElementById('dev').value;
    document.getElementById('sbmt').disabled = true;
    if (!project.length) {
        frn.innerText = "Please select a project";
        return
    }
    if (refresh) {
        document.getElementById('commit').value = `commits@${project}.apache.org`;
        document.getElementById('dev').value = `dev@${project}.apache.org`;
    }
    if (!suffix.match(/^[-a-z0-9]*$/)) {
        frn.innerText = "Invalid repository suffix. Must be alphanumeric characters or dashes only.";
        return
    }
    if (login_cached.podlings.includes(project)) {
        project = 'incubator-' + project;
    }
    let repo_name = project;
    if (suffix && suffix.length) {
        repo_name += "-" + suffix;
    }
    repo_name += ".git";
    let repo_url_gitbox = "https://gitbox.apache.org/repos/" + ( priv ? "private/" + project : "asf") + "/" + repo_name;
    let repo_url_github= "https://github.com/apache/" + repo_name;
    frn.innerText = `This will create a repository named ${repo_name}`;
    document.getElementById('sbmt').disabled = false;
    if (submit) {
        if (window.confirm(`This will create ${repo_name}. Are you sure you wish to continue?`)) {
            create_new_repo(project, repo_name, priv, repo_title, repo_commit, repo_dev);
        }
    }
}


async function create_new_repo(project, name, priv, title, commit, dev) {
    blurbg(true);
    let rv = await POST("api/repository.json" , {
            action: 'create' ,
            repository: name,
            private: priv,
            title: title,
            commit: commit,
            issue: dev
        });
    blurbg(false);
    if (rv.okay == true) {
        let canvas = document.getElementById('main');
        let repo_url_gitbox = "https://gitbox.apache.org/repos/" + ( priv ? "private/" + project : "asf") + "/" + name;
        let repo_url_github= "https://github.com/apache/" + name;
        canvas.innerText = 'Your repository has been created and will be available for use within a few minutes.';
        canvas.appendChild(br());
        canvas.appendChild(document.createTextNode("Your project is available on gitbox at: "));
        let gburl = document.createElement('a');
        gburl.setAttribute("href" ,repo_url_gitbox);
        gburl.innerText = repo_url_gitbox;
        canvas.appendChild(gburl);
        canvas.appendChild(br());
        canvas.appendChild(document.createTextNode("Your project is available on GitHub at: "));
        let ghurl = document.createElement('a');
        ghurl.setAttribute("href" ,repo_url_github);
        ghurl.innerText = repo_url_github;
        canvas.appendChild(ghurl);
        canvas.appendChild(br());
        canvas.appendChild(document.createTextNode("User permissions should be set up within the next five minutes. If not, please let us know at: users@infra.apache.org"));

    } else {
        alert(rv.message);
    }
}


async function prime() {

    let canvas = document.getElementById('main');

    let formdata = {};
    let matches = location.search.match(/[^?=&]+=[^&]+/g);
    if (matches) {
        matches.reduce((acc, value) => {
                let a = value.split("=", 2);
                formdata[a[0]] = decodeURIComponent(a[1]);
            }, 10
        );
    }
    // Fetch prefs, see if we're authed
    let login = await GET("api/preferences.json");
    login_cached = login;

    // If OAuth call, bypass the prefs check
    if (formdata.action == "oauth") {
        oauth = await POST("api/oauth.json", formdata);
        if (oauth.okay) {
            location.href = "/boxer/";
            return
        } else {
            alert("Something went wrong... :(");
        }
    }

    // Otherwise, if not logged in yet, go to OAuth
    else if (!login.credentials.uid) {
        let oauth_url = encodeURIComponent(`https://${hostname}/boxer/?action=oauth&state=` + state);
        location.href = "https://oauth.apache.org/auth?redirect_uri=" + oauth_url + "&state=" + state;
        return
    }



    if (!formdata.action || formdata.action == 'preferences') {
        // Not authed via GitHub yet
        if (!login.github || !login.github.login) {
            setup_step_one_github_auth(canvas, login);
            return
        }

        // Authed via GitHub but not in Apache Org yet
        if (login.credentials && !login.credentials.github_org_member) {
            setup_step_two_github_org(canvas, login);
            return
        }

        // MFA not enabled yet
        if (!login.github.mfa) {
            setup_step_three_mfa(canvas, login);
            return
        }
        show_page_profile(canvas, login);
        return
    } else if (formdata.action == 'search') {
        search_page(canvas, formdata.query||"");
    } else if (formdata.action == 'newrepo') {
        new_repo_prompt(canvas, login);
    }
}



function begin_oauth_github() {
    let oauth_url = encodeURIComponent(`https://${hostname}/boxer/?action=oauth&key=github&state=` + state);
    let ghurl = `https://github.com/login/oauth/authorize?client_id=${gh_client_id}&redirect_uri=${oauth_url}`;
    console.log(ghurl);
    location.href = ghurl;
}
