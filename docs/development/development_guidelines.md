# Development Guidelines

It is recommended that all Python projects are updated and maintained in the
following way. These guidelines are adapted from those for
[PCDS](https://pcdshub.github.io/development.html). There are many helpful
tutorials online like [this](https://guides.github.com/introduction/flow) if
you want more information.

Creating a Local Checkout
=========================

If you want to make changes to a repository, the first step is to create your
own fork. This allows you to create feature branches without cluttering the
main repository. It also assures that the main repository is only added to by
Pull Request and review. Repositories can be forked from the GitHub site like
`this <https://help.github.com/articles/fork-a-repo>`__. Once this repository is
created, you can clone into your own workspace.

```
git clone https://github.com/YOUR-USERNAME/REPOSITORY.git
```

Now, that we have a copy of the repository create a branch for the feature or
bug you would like to work on.

```
$ git checkout -b my-feature
$ git status
On branch my-feature
nothing to commit, working tree clean
```

Commit Guidelines
=================

Now you are ready to start working! Make changes to files and commit them to
your new branch. We like to prefix our commit messages with a descriptor code.
This makes it easier for someone reviewing the commit history to see what you
have done. These are borrowed from the
[NumPy](https://numpy.org/devdocs/dev/development_workflow.html) project.

## Writing the Commit message development documentation

| Code  | Description                                                                                          |
| ----- | ---------------------------------------------------------------------------------------------------- |
| API   | an (incompatible) API change                                                                         |
| BLD   | change related to building                                                                           |
| FIX   | bug fix                                                                                              |
| DEP   | deprecate something, or remove a deprecated object                                                   |
| DEV   | development tool or utility                                                                          |
| DOC   | documentation                                                                                        |
| ENH   | enhancement                                                                                          |
| MAINT | maintenance commit (refactoring, typos, etc.). MNT is the older form of this and is also acceptable. |
| REV   | revert an earlier commit                                                                             |
| STY   | style fix (whitespace, PEP8, reformatting)                                                           |
| TST   | addition or modification of tests                                                                    |
| REL   | related to releasing your package                                                                    |
| WIP   | commit that is a work in progress                                                                    |

It is also helpful to write docstrings within classes and functions. These are
later converted by mkdocs into HTML documentation. They also are a valuable
tool for exploration of a codebase within an IPython terminal. Docstrings
should follow the form described in the [numpy
documentation](https://numpydoc.readthedocs.io/en/latest/format.html)

Merging Changes
===============

Once you are happy with your code, `push` it back to your fork on GitHub.

```
git push origin my-feature
```

You should now be able to create a Pull Request back to the original
repository. **You should never commit directly back to the original
repository**. In fact, if you are creating a new repository it is possible to
strictly disallow this by explicitly protecting certain branches from direct
commits. We feel strongly that Pull Requests are necessary because they:

- Allow other collaborators to view the changes you made, and give feedback.
- Leave an easily understood explanation to why these changes are necessary.

Once these changes are deemed acceptable to enter the main repository, the
Pull Request can be merged.

Syncing your Local Checkout
===========================

Inevitably, changes to the upstream repository will occur and you will need to
update your local checkout to reflect those. The first step is to make your
local checkout aware of the upstream repository. If this is done correctly, you
should see something like this:

```
$ git remote add upstream https://github.com/UPSTREAM-ORG/REPOSITORY.git
$ git remote -v
origin   https://github.com/YOUR-USERNAME/REPOSITORY.git (fetch)
origin   https://github.com/YOUR-USERNAME/REPOSITORY.git (push)
upstream https://github.com/UPSTREAM-ORG/REPOSITORY.git (fetch)
upstream https://github.com/UPSTREAM-ORG/REPOSITORY.git (push)
```

Now, we need to fetch any changes from the upstream repository. `git fetch`
will grab the latest commits that were merged since we made our own fork

```
git fetch upstream
```

Ideally, you haven't made any changes to your `main` branch. So you should
be able to merge the latest `main` branch from the upstream repository
without concern. All you need to do is switch to your `main` branch and
pull in the changes from the upstream remote. It is usually a good idea to push
these changes back to your fork as well.

```
git checkout main
git pull upstream main
git push origin main
```

Finally, we need to update our feature-branch to have the new changes. Here we
use a `git rebase` to take our local changes. This will remove them
temporarily, pull the upstream changes into our branch, and then re-add our
local changes onto the tip of the commit history. This avoids extraneous merge
commits that clog the commit history of the branch. A more in-depth discussion
can be found [here](https://www.atlassian.com/git/tutorials/merging-vs-rebasing)

This process should look like this:

```
git checkout my-feature
git rebase upstream/main
```

This process should not be done if you think that anyone else is also working
on that branch. The rebasing process re-writes the commit history so any other
checkout of the same branch referring to the old history will create duplicates
of all the commits.
