import re
import sys
from phabricator import Phabricator
import requests
import getopt

def get_latest_release_filename(url):
    """Downloads the release index and gets the file name of the lattest release"""
    try:
        response = requests.get(url)
        response.raise_for_status()
        content = response.text
        found_toctree = False
        for line in content.splitlines():
            if '.. toctree::' in line:
                found_toctree = True
                continue
            if found_toctree:
                stripped_line = line.strip()
                if stripped_line and not stripped_line.startswith(':'):
                    return stripped_line
        print("Error: Could not find '.. toctree::' block.", file=sys.stderr)
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error downloading index file: {e}", file=sys.stderr)
        return None

def parse_release_notes(url):
    """Downloads a specific release notes file and parses the bug list."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        content = response.text

        bug_list = []
        in_changes_section = False
        in_container_block = False

        for line in content.splitlines():
            # Find the start of the "Changes" section
            if '`Changes in NSS' in line:
                in_changes_section = True
                continue

            # Once in the right section, find the container block
            if in_changes_section and '.. container::' in line:
                in_container_block = True
                continue

            if in_container_block:
                # An unindented line means the block has ended
                if line and not line.startswith(' '):
                    break
                # Add indented lines to our list
                if line.strip():
                    bug_list.append(line.strip())

        return "\n".join(bug_list)

    except requests.exceptions.RequestException as e:
        print(f"Error downloading release notes: {e}", file=sys.stderr)
        return ""

def search_phabricator_revision(phab_client, title):
    """Searches for a Phabricator revision by its title."""
    try:
        for t in [title, title[:-1], title.replace(" - ", " ", 1), title[:-1].replace(" - ", " ", 1)]:
            results = phab_client.differential.revision.search(constraints={"query": f'"{t}"'})
            if results.get('data'):
                return results['data'][0]['fields']['uri']
        return "No Phabricator revision found."
    except Exception as e:
        return f"Phabricator API Error: {e}"

def format_release_to_filename(version_str):
    """Converts a version string like '3.116.0' or '3.116.1' to 'nss_3_116.rst' or 'nss_3_116_1.rst'."""
    parts = version_str.split('.')
    # If the last part is '0' and it's not a simple two-part version (e.g. "3.0"), remove it.
    if len(parts) > 2 and parts[-1] == '0':
        parts.pop()

    formatted_version = "_".join(parts)
    return f"nss_{formatted_version}.rst"

def usage():
        print(sys.argv[0] + ' [-r|--release release] [-h|--help]')
        print("    release in the form 3.16 3.16.0 3.16.1")

if __name__ == "__main__":
    print(80*'-')
    print("\n    NSS scoping preper\n")
    print(80*'-')
    print()

    config_file = "./config"
    config = {}

    phabricator_token = None
    phabricator_host = 'https://phabricator.services.mozilla.com/api/'

    nss_releases_index_url = 'https://hg-edge.mozilla.org/projects/nss/raw-file/default/doc/rst/releases/index.rst'
    nss_releases_base_url = 'https://hg-edge.mozilla.org/projects/nss/raw-file/default/doc/rst/releases/'

    release = None

    # check arguments
    try:
        opts, args = getopt.getopt(sys.argv[1:],"r:h",["help", "release"])
    except getopt.GetoptError as err:
        print(err)
        usage()
        sys.exit(2)

    # load config
    for config_line in open(config_file, 'r'):
        if len(config_line) < 2 or config_line[0] == '#':
            continue
        (key, value) = config_line.strip().split(':',1)
        config[key]=value.strip()
        if key == 'phabricator-api':
            phabricator_token = value.strip()
        elif key == 'release':
            release = format_release_to_filename(value.strip())
        else:
            print(f"unknown configuration field: '{key}' found in '{config_file}'")
            sys.exit(2)

    # load arguments
    for opt, arg in opts:
        if opt == '-r' or opt == '--release':
            release = format_release_to_filename(arg)
        elif opt == '-h' or opt == '--help':
            usage()
            exit()

    # connect to phabricator
    try:
        phab = Phabricator(host=phabricator_host, token=phabricator_token)
        phab.update_interfaces()
    except Exception as e:
        print(f"Error initializing Phabricator client: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Find the latest release notes file unless specified
    print("Finding latest release file...")
    if release is None:
        release = get_latest_release_filename(nss_releases_index_url)
    if not release:
        sys.exit(1)

    release_notes_url = nss_releases_base_url + release
    print(f"Found: {release}\n")

    # 3. Parse the bug list from that file
    print("Parsing release notes...")
    release_notes_text = parse_release_notes(release_notes_url)
    if not release_notes_text:
        print("Could not extract any bugs from the release notes.", file=sys.stderr)
        sys.exit(1)
    print("Done parsing.\n")

    # 4. Process each bug line
    bug_id_pattern = re.compile(r"Bug\s+(\d+)")
    processed_bugs = set()

    print(80*'-')
    print(release[:-4])
    print('')

    # Group all release note lines by their bug ID
    bug_id_pattern = re.compile(r"Bug\s+(\d+)")
    grouped_bugs = {}
    for line in release_notes_text.strip().split('\n'):
        clean_line = line.lstrip("- ")
        match = bug_id_pattern.search(clean_line)
        if match:
            bug_id = match.group(1)
            if bug_id not in grouped_bugs:
                grouped_bugs[bug_id] = []
            grouped_bugs[bug_id].append(clean_line)

    # Process each group of bugs together and print them
    for bug_id in sorted(grouped_bugs.keys(), key=int):
        lines = grouped_bugs[bug_id]
        mult = True if len(lines) > 1 else False

        if mult:
            print("---")
            print(f"Bug {bug_id} - https://bugzilla.mozilla.org/show_bug.cgi?id={bug_id}")
        else:
            print(lines[0])
            print("\t"+f"https://bugzilla.mozilla.org/show_bug.cgi?id={bug_id}")

        for i, line in enumerate(lines):
            if mult:
                print("\n"+line)

            phab_link = search_phabricator_revision(phab, line)
            print("\t"+phab_link)

        if mult:
            print("---")
        print()

