# Screenshots

Drop PNG/JPG screenshots in this directory using the exact filenames referenced
from the project root `README.md`:

| File | Capture from | Recommended size |
|------|--------------|------------------|
| `hero.png` | The annotation workspace mid-edit (left: DocList tabs, center: DocViewer with highlighted source text, right: ReferenceCard with kanun_no + madde filled) | 1600×900, cropped |
| `feed.png` | The 3-tab feed (Yeni / Devam Eden / Tamamlanan) with a mix of workflow_states visible — at least one `draft` and one `verified` row | 1200×800 |
| `annotate.png` | The 60/40 split: DocViewer on the left, ReferencePanel with 2-3 reference cards on the right | 1400×900 |
| `training.png` | The training quiz step or the 3-doc training flow with progress indicator | 1200×800 |
| `admin.png` | Admin panel users table — promote/demote action visible | 1200×800 |

## Tips

- Use a clean test user (no real names in audit log strips).
- Capture with the system theme that reads best in your README (default is light).
- PNG with transparent background looks cleanest on GitHub's light + dark themes;
  if your tool emits white-background JPG that's fine too.
- Keep file sizes under ~500 KB each — GitHub doesn't compress images and the
  page weight adds up.

## Optional extras

If you add more screenshots, reference them from the main README by editing the
`Screenshots` section. Suggested follow-ups:

- `gamification.png` — XP badge / streak banner
- `lock-conflict.png` — LockConflictModal showing the other user's name
- `version-chain.png` — annotation chain UI with create → edit → complete_mark
