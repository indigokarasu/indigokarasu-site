# indigokarasu-site

<p align="center">
  <img src="./assets/readme/hero.jpg" width="100%" alt="Source for indigokarasu.com">
</p>

Source for the public-facing site indigokarasu.com.

**Contents:**
- `public/`: the site as served (one static page, favicon, share image, robots.txt, sitemap)
- `build-activity.py`: builds `public/activity.json`, the recent public GitHub activity shown on the page
- Published via DreamHost; the activity feed is rebuilt hourly

To preview locally:

```sh
python3 build-activity.py --out public/activity.json
python3 -m http.server --directory public
```

---
## 📄 License
MIT License - see `LICENSE` for details.
